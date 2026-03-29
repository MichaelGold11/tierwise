"""
simulation.py — Agent decision engine.

Each agent evaluates each paid tier using:

  conversion_probability =
    financial_feasibility
    × behavioral_receptivity       ← agent's dominant psychological mode
    × framing_match_score          ← HOW WELL the tier's actual copy matches that mode
    × (1 - penalties)

The key insight: framing_match_score is computed from the FRAMING SIGNALS
extracted by Claude from the real pricing document — not just feature counts.

Examples:
  - Social Follower agent + tier with "social_proof" signal → framing_match_score boost
  - Anxious Planner agent + tier with "loss_framing" signal → boost
  - Spontaneous Mover agent + high complexity_score tier    → penalty
  - Authority Truster agent + "authority" signal            → boost
"""

import random
from typing import List, Dict, Any


# ── Framing signal → agent attribute mapping ──────────────────────────────

SIGNAL_RECEPTIVITY_MAP = {
    'social_proof':  'social_proof_receptivity',
    'loss_framing':  'loss_framing_receptivity',
    'authority':     'authority_receptivity',
    'scarcity':      'scarcity_sensitivity',
    'gain_framing':  'openness',            # open/curious agents respond to gain framing
    'simplicity':    None,                  # handled separately via cognitive_bandwidth
}


def _framing_match_score(agent: dict, tier: dict) -> float:
    """
    Compute how well this tier's actual copy framing matches this agent's psychology.

    Base score = 0.45 (neutral — agent can always convert on price alone).
    Each matching signal adds a boost weighted by the agent's receptivity.
    High complexity penalizes low cognitive_bandwidth agents.
    """
    score = 0.45
    signals = tier.get('framing_signals', [])
    complexity = float(tier.get('complexity_score', 0.3))

    for signal in signals:
        receptivity_attr = SIGNAL_RECEPTIVITY_MAP.get(signal)
        if receptivity_attr:
            # Each matching signal contributes up to +0.20
            score += agent.get(receptivity_attr, 0.0) * 0.20
        elif signal == 'simplicity':
            # Simplicity helps low-bandwidth agents (inverse of complexity_tolerance)
            score += (1.0 - agent.get('complexity_tolerance', 0.5)) * 0.15

    # Complexity penalty: high complexity tiers hurt low cognitive_bandwidth agents
    cb = agent.get('cognitive_bandwidth', 0.5)
    if complexity > 0.5 and cb < 0.4:
        score *= (0.55 + cb * 0.5)  # scale penalty by how low cb is

    return min(1.0, max(0.1, score))


# ── Financial feasibility ──────────────────────────────────────────────────

def _financial_feasibility(agent: dict, tier_price: float) -> float:
    """
    Returns 0 if price > financial_threshold (hard ceiling).
    Scales from 1.0 (price=0) down to ~0.35 as price approaches threshold.
    """
    if tier_price <= 0:
        return 1.0
    threshold = agent['financial_threshold']
    if tier_price > threshold:
        return 0.0
    ratio = tier_price / threshold
    return 1.0 - (ratio * 0.65)


# ── Per-agent decision ─────────────────────────────────────────────────────

def _decide_tier(agent: dict, tiers: List[Dict]) -> str:
    """
    Run the full decision engine for one agent against all tiers.
    Returns the name of the chosen tier.
    """
    free_tier = next((t for t in tiers if t.get('is_free')), None)
    paid_tiers = [t for t in tiers if not t.get('is_free')]
    default_tier = free_tier['name'] if free_tier else (tiers[0]['name'] if tiers else 'Free')

    if not paid_tiers:
        return default_tier

    best_tier = default_tier
    best_prob = 0.0

    for tier in paid_tiers:
        price = float(tier.get('price_monthly', 0))
        tier_index = tiers.index(tier)
        is_top_tier = tier_index >= 2

        # ── Financial feasibility ─────────────────────────────────────────
        ff = _financial_feasibility(agent, price)
        if ff == 0.0:
            continue

        # ── Behavioral receptivity ────────────────────────────────────────
        lfr = agent['loss_framing_receptivity']
        spr = agent['social_proof_receptivity']
        ar  = agent['authority_receptivity']

        if is_top_tier:
            # Top tier (Team-level): requires decent financial threshold
            if agent['financial_threshold'] < 40:
                continue
            # Needs authority OR social signal to even consider it
            if ar < 0.40 and spr < 0.45:
                continue
            behavioral_receptivity = (ar * 0.55) + (spr * 0.45)
        else:
            # Middle tier (Pro-level): weighted combination of all receptivity modes
            behavioral_receptivity = (lfr * 0.35) + (spr * 0.35) + (ar * 0.30)

        # ── Framing match score (reacts to actual pricing copy) ───────────
        framing_match = _framing_match_score(agent, tier)

        # ── Multiplicative penalties (can never alone push prob to zero) ──
        # Cognitive load: low-bandwidth agents struggle with complex paid tiers
        complexity = float(tier.get('complexity_score', 0.3))
        cb_multiplier = 1.0
        if agent['cognitive_bandwidth'] < 0.4 and complexity > 0.4:
            cb_multiplier = 0.72

        # Price sensitivity drag
        price_mult = 1.0 - (agent['price_sensitivity'] * 0.18)

        # Default stickiness drag (inertia toward staying free)
        stickiness_mult = 1.0 - (agent['default_stickiness'] * 0.15)

        # WTP ceiling: if stated willingness-to-pay is below price, strong reduction
        wtp_mult = 1.0
        if price > agent['wtp_ceiling'] > 0:
            wtp_mult = 0.45

        # ── Final probability ─────────────────────────────────────────────
        prob = (
            ff
            * behavioral_receptivity
            * framing_match
            * cb_multiplier
            * price_mult
            * stickiness_mult
            * wtp_mult
        )
        prob = max(0.0, min(1.0, prob))

        # Stochastic decision
        roll = random.random()
        if roll < prob and prob > best_prob:
            best_prob = prob
            best_tier = tier['name']

    return best_tier


# ── Main simulation entry point ────────────────────────────────────────────

def run_simulation(agents: List[dict], pricing_data: dict) -> Dict[str, Any]:
    """
    Run the full simulation.

    pricing_data is the structured dict from parse_pricing.parse_with_claude(),
    containing tiers with framing_signals, complexity_score, etc.

    Mutates agents in place with chosen_tier and decision_probability.
    Returns the full simulation result dict.
    """
    tiers = pricing_data.get('tiers', [])

    if not tiers:
        tiers = [
            {'name': 'Free', 'price_monthly': 0.0, 'is_free': True, 'framing_signals': [], 'complexity_score': 0.2, 'features': [], 'feature_count': 0},
            {'name': 'Pro', 'price_monthly': 18.0, 'is_free': False, 'framing_signals': ['social_proof'], 'complexity_score': 0.4, 'features': [], 'feature_count': 0},
        ]

    tier_names = [t['name'] for t in tiers]
    free_tier_name = next((t['name'] for t in tiers if t.get('is_free')), tier_names[0])

    # Run decision engine for every agent
    for agent in agents:
        chosen = _decide_tier(agent, tiers)
        agent['chosen_tier'] = chosen

        # Summary probability score for display
        if chosen == free_tier_name:
            agent['decision_probability'] = round(agent['default_stickiness'], 3)
        else:
            tier = next(t for t in tiers if t['name'] == chosen)
            ff = _financial_feasibility(agent, float(tier.get('price_monthly', 0)))
            br = (agent['loss_framing_receptivity'] + agent['social_proof_receptivity'] + agent['authority_receptivity']) / 3.0
            agent['decision_probability'] = round(min(1.0, ff * br), 3)

    # ── Build summary ──────────────────────────────────────────────────────
    n = len(agents)
    tier_counts = {name: 0 for name in tier_names}
    for agent in agents:
        ct = agent['chosen_tier']
        tier_counts[ct] = tier_counts.get(ct, 0) + 1

    tier_pcts = {name: round(cnt / n * 100, 1) for name, cnt in tier_counts.items()}

    # Projected MRR
    projected_mrr = 0.0
    for t in tiers:
        if not t.get('is_free'):
            projected_mrr += tier_counts.get(t['name'], 0) * float(t.get('price_monthly', 0))

    # Archetype breakdown
    archetype_colors = {
        'Anxious Planner':    '#EF4444',
        'Social Follower':    '#3B82F6',
        'Spontaneous Mover':  '#F97316',
        'Authority Truster':  '#22C55E',
        'Indifferent Drifter':'#A855F7',
    }
    archetypes = list(archetype_colors.keys())

    by_archetype = {}
    for arch in archetypes:
        arch_agents = [a for a in agents if a['archetype'] == arch]
        arch_n = len(arch_agents)
        if arch_n == 0:
            by_archetype[arch] = {'count': 0, 'pct': 0, 'color': archetype_colors[arch], 'tiers': {}, 'conversion_rate': 0}
            continue

        arch_tier_counts = {name: 0 for name in tier_names}
        for a in arch_agents:
            arch_tier_counts[a['chosen_tier']] = arch_tier_counts.get(a['chosen_tier'], 0) + 1

        converted = arch_n - arch_tier_counts.get(free_tier_name, 0)
        conversion_rate = round(converted / arch_n * 100, 1)

        by_archetype[arch] = {
            'count': arch_n,
            'pct': round(arch_n / n * 100, 1),
            'color': archetype_colors[arch],
            'conversion_rate': conversion_rate,
            'tiers': {name: round(c / arch_n * 100, 1) for name, c in arch_tier_counts.items()},
        }

    # Tier summary list
    tier_summary = []
    for t in tiers:
        name = t['name']
        count = tier_counts.get(name, 0)
        mrr_contribution = count * float(t.get('price_monthly', 0)) if not t.get('is_free') else 0.0

        # Which archetype converts most on this tier
        top_arch = None
        top_arch_rate = 0.0
        for arch, data in by_archetype.items():
            rate = data['tiers'].get(name, 0)
            if rate > top_arch_rate and name != free_tier_name:
                top_arch_rate = rate
                top_arch = arch

        tier_summary.append({
            'name': name,
            'price_monthly': float(t.get('price_monthly', 0)),
            'price_annual': t.get('price_annual'),
            'feature_count': t.get('feature_count', 0),
            'features': t.get('features', []),
            'value_proposition': t.get('value_proposition', ''),
            'framing_signals': t.get('framing_signals', []),
            'complexity_score': t.get('complexity_score', 0.3),
            'badge': t.get('badge'),
            'highlighted': t.get('highlighted', False),
            'count': count,
            'pct': tier_pcts.get(name, 0),
            'mrr_contribution': round(mrr_contribution, 2),
            'top_converting_archetype': top_arch,
            'is_free': t.get('is_free', False),
        })

    # Signal effectiveness: which framing signals are present and working
    signal_effectiveness = _compute_signal_effectiveness(agents, tiers, free_tier_name)

    return {
        'agents': agents,
        'summary': {
            'total_agents': n,
            'product_name': pricing_data.get('product_name', 'Your Product'),
            'tier_counts': tier_counts,
            'tier_pcts': tier_pcts,
            'by_archetype': by_archetype,
            'projected_mrr': round(projected_mrr, 2),
            'pricing_structure': tier_summary,
            'free_tier_name': free_tier_name,
            'overall_conversion_rate': round((n - tier_counts.get(free_tier_name, 0)) / n * 100, 1),
            'signal_effectiveness': signal_effectiveness,
            'has_annual_option': pricing_data.get('has_annual_option', False),
            'overall_complexity': pricing_data.get('overall_complexity', 0.4),
        },
    }


def _compute_signal_effectiveness(agents, tiers, free_tier_name):
    """
    For each framing signal present in any tier, compute:
    - avg conversion rate of agents most receptive to that signal
    - vs avg conversion rate of agents less receptive
    This shows which signals are actually moving the needle.
    """
    all_signals = set()
    for t in tiers:
        all_signals.update(t.get('framing_signals', []))

    effectiveness = {}
    for signal in all_signals:
        receptivity_attr = SIGNAL_RECEPTIVITY_MAP.get(signal, 'openness')
        if not receptivity_attr:
            receptivity_attr = 'cognitive_bandwidth'

        receptive = [a for a in agents if a.get(receptivity_attr, 0) >= 0.55]
        non_receptive = [a for a in agents if a.get(receptivity_attr, 0) < 0.55]

        def conv_rate(group):
            if not group:
                return 0.0
            converted = sum(1 for a in group if a.get('chosen_tier') != free_tier_name)
            return round(converted / len(group) * 100, 1)

        effectiveness[signal] = {
            'receptive_conversion': conv_rate(receptive),
            'non_receptive_conversion': conv_rate(non_receptive),
            'lift': round(conv_rate(receptive) - conv_rate(non_receptive), 1),
            'receptive_count': len(receptive),
        }

    return effectiveness
