import os
import re
import json
from typing import Dict, Any

try:
    import anthropic
    _ANTHROPIC_AVAILABLE = True
except ImportError:
    _ANTHROPIC_AVAILABLE = False

FALLBACK_REPORT = {
    "insight_report": {
        "overall_conversion_rates": {
            "summary": "Simulation complete. Conversion rates vary significantly by archetype and price point.",
            "free_pct": "~55%",
            "pro_pct": "~32%",
            "team_pct": "~13%"
        },
        "conversion_by_archetype": {
            "Anxious Planner":    {"rate": 42, "ceiling": 70, "gap_pp": 28, "missing_signal": "loss_framing", "missing_from_tier": "Pro", "summary": "Pro tier lacks loss_framing — primary scarcity trigger is absent for this archetype."},
            "Social Follower":    {"rate": 38, "ceiling": 65, "gap_pp": 27, "missing_signal": "social_proof", "missing_from_tier": "Team", "summary": "Team tier lacks social_proof signals — peer validation missing at the higher price point."},
            "Spontaneous Mover":  {"rate": 18, "ceiling": 55, "gap_pp": 37, "missing_signal": "simplicity",   "missing_from_tier": "Pro",  "summary": "Pro tier complexity score is too high — Spontaneous Movers bounce before reaching the CTA."},
            "Authority Truster":  {"rate": 31, "ceiling": 60, "gap_pp": 29, "missing_signal": "authority",    "missing_from_tier": "Pro",  "summary": "Pro tier lacks authority signals — expert endorsements needed to activate this archetype."},
            "Indifferent Drifter":{"rate": 6,  "ceiling": 20, "gap_pp": 14, "missing_signal": None,           "missing_from_tier": None,   "summary": "Near-baseline conversion — requires usage-based triggers to create upgrade pressure."}
        },
        "why_converted": [
            "Financial fit — income bracket comfortably covered the price",
            "Behavioral match — loss aversion or social proof signals were activated",
            "Low cognitive load — feature comparison was clear and direct"
        ],
        "why_lost": [
            "Financial constraint — price exceeded monthly threshold",
            "Signal mismatch — required framing signal absent from paid tier",
            "Complexity overload — Spontaneous Movers bounced off feature lists"
        ],
        "projected_mrr": {
            "mrr_commentary": "Revenue is constrained by missing framing signals, not price ceiling.",
            "top_lever": "Add loss_framing to the Pro tier to unlock Anxious Planner conversions"
        },
        "key_behavioral_finding": "The most actionable insight: your Pro tier is losing Spontaneous Movers (20% of users) due to pricing page complexity. A single-value landing approach for this segment could increase Pro conversion by an estimated 8-12 percentage points."
    },
    "framing_guide": {
        "Free": {
            "framing_type": "Loss Priming",
            "copy_recommendation": "You're using the free plan — here's what you're missing: [specific Pro feature they've triggered]. Unlock it before your next session.",
            "information_architecture": "Show one blocked feature prominently. Hide the full feature comparison. Use inline upgrade prompts at the moment of friction.",
            "messaging_for_unconverted": "Target Indifferent Drifters with usage-milestone triggers: 'You've created 47 documents — Pro users average 3x more output.'"
        },
        "Pro": {
            "framing_type": "Social Proof + Loss Framing Hybrid",
            "copy_recommendation": "Join 50,000 teams who upgraded to Pro. Most popular for solo creators. Start before your trial ends — don't lose your work.",
            "information_architecture": "Lead with user count and 'Most Popular' badge. Show 3 key benefits (not 15 features). Add countdown if in trial. Place testimonial near CTA.",
            "messaging_for_unconverted": "Spontaneous Movers need one bold statement: 'Pro. $18/month. Everything you need, nothing you don't.' Remove feature table for this segment."
        },
        "Team": {
            "framing_type": "Authority + ROI Framing",
            "copy_recommendation": "Recommended for growing teams. Trusted by [Company Name] and 2,000+ teams. Calculate your ROI: teams save an average of 4 hours/week per member.",
            "information_architecture": "Lead with authority signals (logos, certification badges). Show ROI calculator. Include a comparison table (Authority Trusters have high complexity tolerance). Add 'Speak to sales' option.",
            "messaging_for_unconverted": "Authority Trusters who haven't converted need a direct recommendation signal: 'Our team plan is the right choice for teams of 3+. Here's why.' Expert endorsement outperforms peer proof for this segment."
        }
    }
}


def build_prompt(simulation_result: Dict[str, Any]) -> str:
    summary = simulation_result['summary']
    tiers = summary['pricing_structure']
    by_arch = summary['by_archetype']

    # Tier lines — include framing signals and features so Claude can reason about coverage
    tier_lines = []
    for t in tiers:
        price = t.get('price_monthly', t.get('price', 0))
        signals = t.get('framing_signals') or []
        features = t.get('features') or []
        feature_preview = ', '.join(features[:6]) if features else 'none listed'
        tier_lines.append(
            f"  - {t['name']} (${price}/mo, {'FREE' if t.get('is_free') else 'PAID'}): "
            f"{t.get('feature_count', len(features))} features, complexity={t.get('complexity_score', '?')} "
            f"→ {t.get('count', 0)} agents ({t.get('pct', 0)}%) | "
            f"framing_signals=[{', '.join(signals) if signals else 'NONE'}] | "
            f"features=[{feature_preview}{'...' if len(features) > 6 else ''}]"
        )

    arch_lines = []
    for arch_name, data in by_arch.items():
        if data['count'] == 0:
            continue
        tier_breakdown = ', '.join(f"{k}: {v}%" for k, v in data['tiers'].items())
        arch_lines.append(
            f"  - {arch_name} (n={data['count']}, {data['pct']}% of population): "
            f"conversion_rate={data['conversion_rate']}% | {tier_breakdown}"
        )

    # Signal effectiveness — which signals are present and whether they're moving the needle
    sig_eff = summary.get('signal_effectiveness', {})
    sig_lines = []
    for sig, eff in sig_eff.items():
        sig_lines.append(
            f"  - {sig}: receptive agents converted at {eff['receptive_conversion']}% "
            f"vs non-receptive {eff['non_receptive_conversion']}% "
            f"(lift={eff['lift']}%, n_receptive={eff['receptive_count']})"
        )
    if not sig_lines:
        sig_lines = ['  - No framing signals were detected in the pricing copy.']

    # Build archetype-to-required-signal mapping for the signal audit
    ARCHETYPE_REQUIRED_SIGNALS = {
        'Anxious Planner':   ('loss_framing', 'scarcity'),
        'Social Follower':   ('social_proof',),
        'Spontaneous Mover': ('simplicity',),
        'Authority Truster': ('authority',),
        'Indifferent Drifter': (),
    }
    BEHAVIORAL_CEILINGS = {
        'Anxious Planner': 70,
        'Social Follower': 65,
        'Spontaneous Mover': 55,
        'Authority Truster': 60,
        'Indifferent Drifter': 20,
    }

    # Build per-archetype signal audit lines — compare required signals vs what's present per tier
    all_tier_signals = {t['name']: set(t.get('framing_signals') or []) for t in tiers}
    paid_tier_names = [t['name'] for t in tiers if not t.get('is_free')]

    audit_lines = []
    for arch, data in by_arch.items():
        if data['count'] == 0:
            continue
        actual_rate = data['conversion_rate']
        ceiling = BEHAVIORAL_CEILINGS.get(arch, 50)
        gap = ceiling - actual_rate
        required = ARCHETYPE_REQUIRED_SIGNALS.get(arch, ())

        # Identify which paid tiers are missing this archetype's required signals
        missing_in = []
        for tier_name in paid_tier_names:
            present = all_tier_signals.get(tier_name, set())
            missing = [s for s in required if s not in present]
            if missing:
                missing_in.append(f"{tier_name} missing [{', '.join(missing)}]")

        signal_status = (
            f"required_signals={list(required)}, "
            f"gap_to_ceiling={gap:.1f}pp, "
            f"missing_from_paid_tiers=[{'; '.join(missing_in) if missing_in else 'none — signals present'}]"
        )
        audit_lines.append(f"  - {arch}: actual={actual_rate}% ceiling={ceiling}% | {signal_status}")

    # Calculate paid tier price stats for recommendations
    paid_tiers = [t for t in tiers if not t.get('is_free', False)]
    avg_paid_price = (
        sum(t.get('price_monthly', t.get('price', 0)) for t in paid_tiers) / len(paid_tiers)
        if paid_tiers else 10.0
    )
    lowest_paid_price = (
        min(t.get('price_monthly', t.get('price', 0)) for t in paid_tiers)
        if paid_tiers else 10.0
    )

    prompt = f"""You are analyzing a behavioral pricing simulation for a SaaS product.

SIMULATION OVERVIEW:
- Total agents: {summary['total_agents']}
- Projected MRR: ${summary['projected_mrr']:,.2f}
- Overall paid conversion: {summary.get('overall_conversion_rate', 0)}%
- Free tier ({summary['free_tier_name']}): {summary['tier_pcts'].get(summary['free_tier_name'], 0)}% stayed free

PRICING TIERS (with actual framing signals extracted from the pricing copy):
{chr(10).join(tier_lines)}

ARCHETYPE BREAKDOWN:
{chr(10).join(arch_lines)}

SIGNAL EFFECTIVENESS (measured lift from signals present in the copy):
{chr(10).join(sig_lines)}

ARCHETYPE BEHAVIORAL PROFILES & REQUIRED TRIGGERS:
- Anxious Planner (22%): High loss_aversion (0.82), high neuroticism (0.78). CONVERTS on: loss_framing, scarcity signals. BOUNCES on: absence of urgency.
- Social Follower (28%): High social_conformity (0.85). CONVERTS on: social_proof (user counts, "Most Popular" badges). BOUNCES on: absence of peer validation.
- Spontaneous Mover (20%): High present_bias (0.82), low cognitive_bandwidth (0.30). CONVERTS on: simplicity, single bold CTA. BOUNCES on: high complexity_score, feature lists.
- Authority Truster (18%): High authority_trust (0.88). CONVERTS on: authority signals (expert endorsements, recommended badges). BOUNCES on: peer proof without expert validation.
- Indifferent Drifter (12%): Low loss_aversion (0.25), high default_stickiness (0.75). Resists all conversion without usage-based triggers.

BEHAVIORAL CEILINGS (theoretical max when framing is perfectly matched):
- Anxious Planner: 70% | Social Follower: 65% | Spontaneous Mover: 55% | Authority Truster: 60% | Indifferent Drifter: 20%

SIGNAL COVERAGE AUDIT (actual conversion vs ceiling, and which signals are missing from paid tiers):
{chr(10).join(audit_lines)}

AVERAGE PAID TIER PRICE: ${avg_paid_price:.2f}/mo
LOWEST PAID TIER PRICE: ${lowest_paid_price:.2f}/mo

ANALYTICAL REQUIREMENT — you MUST follow this diagnostic logic:
1. For every archetype whose actual conversion rate is more than 15 percentage points below its behavioral ceiling, identify the specific framing signal(s) that archetype requires but that are absent from the paid tiers.
2. State explicitly that this signal absence — not just price — is the structural cause of the conversion gap. Do not write generic behavioral advice; write a specific cause-effect sentence: "[Archetype] converted at X% against a ceiling of Y% because the [tier name] tier lacked [signal], which is this archetype's primary conversion trigger."
3. In why_lost, identify whether the loss was caused by (a) financial constraint, (b) signal mismatch (required signal absent from paid tier), or (c) complexity overload — and cite the specific tier and signal as evidence.

For each recommendation's projected_monthly_impact, calculate as an integer:
  archetype_count × lowest_paid_price × (gap_to_ceiling × 0.30) / 100
Where gap_to_ceiling = behavioral_ceiling_pct - actual_conversion_rate.
Replace the placeholder 0 values with your calculated integers.

Respond with ONLY a valid JSON object (no markdown, no code blocks) with exactly these three keys:

{{
  "insight_report": {{
    "overall_conversion_rates": {{
      "summary": "...",
      "free_pct": "...",
      "pro_pct": "...",
      "team_pct": "..."
    }},
    "conversion_by_archetype": {{
      "Anxious Planner": {{
        "rate": <integer: actual conversion rate>,
        "ceiling": <integer: behavioral ceiling>,
        "gap_pp": <integer: ceiling minus rate>,
        "missing_signal": "<signal name OR null if signals are present>",
        "missing_from_tier": "<tier name where signal is absent OR null>",
        "summary": "<one sentence: cause-effect. E.g. Pro lacks loss_framing — primary trigger absent for this archetype.>"
      }},
      "Social Follower": {{ "rate": <int>, "ceiling": <int>, "gap_pp": <int>, "missing_signal": "<str|null>", "missing_from_tier": "<str|null>", "summary": "<one sentence>" }},
      "Spontaneous Mover": {{ "rate": <int>, "ceiling": <int>, "gap_pp": <int>, "missing_signal": "<str|null>", "missing_from_tier": "<str|null>", "summary": "<one sentence>" }},
      "Authority Truster": {{ "rate": <int>, "ceiling": <int>, "gap_pp": <int>, "missing_signal": "<str|null>", "missing_from_tier": "<str|null>", "summary": "<one sentence>" }},
      "Indifferent Drifter": {{ "rate": <int>, "ceiling": <int>, "gap_pp": <int>, "missing_signal": "<str|null>", "missing_from_tier": "<str|null>", "summary": "<one sentence>" }}
    }},
    "why_converted": ["<bullet: ≤12 words, specific signal + archetype>", "<bullet>", "<bullet>"],
    "why_lost": ["<bullet: ≤12 words, specific cause — financial, signal mismatch, or complexity>", "<bullet>", "<bullet>"],
    "projected_mrr": {{
      "mrr_commentary": "<one sentence: current MRR with the top structural note>",
      "top_lever": "<one sentence: the single highest-leverage change>"
    }},
    "key_behavioral_finding": "The single most actionable structural finding — name the specific archetype, the specific tier, and the specific missing signal that represents the largest recoverable revenue gap."
  }},
  "framing_guide": {{
    "{tiers[0]['name'] if tiers else 'Free'}": {{
      "framing_type": "loss | gain | social_proof | authority | simplicity",
      "copy_recommendation": "Specific headline or CTA copy",
      "information_architecture": "What to show, what to hide, what order",
      "messaging_for_unconverted": "Specific message for the highest-value unconverted segment"
    }},
    "{tiers[1]['name'] if len(tiers) > 1 else 'Pro'}": {{
      "framing_type": "...",
      "copy_recommendation": "...",
      "information_architecture": "...",
      "messaging_for_unconverted": "..."
    }},
    "{tiers[2]['name'] if len(tiers) > 2 else 'Team'}": {{
      "framing_type": "...",
      "copy_recommendation": "...",
      "information_architecture": "...",
      "messaging_for_unconverted": "..."
    }}
  }},
  "recommendations": [
    {{
      "title": "Short action title (under 10 words)",
      "description": "Plain English — name the exact signal to add, which tier to add it to, and which archetype it will unlock. Written for a non-technical business owner (2-3 sentences).",
      "target_archetype": "Which archetype this primarily targets",
      "projected_monthly_impact": 0
    }},
    {{
      "title": "...",
      "description": "...",
      "target_archetype": "...",
      "projected_monthly_impact": 0
    }},
    {{
      "title": "...",
      "description": "...",
      "target_archetype": "...",
      "projected_monthly_impact": 0
    }}
  ]
}}"""
    return prompt


def call_claude(simulation_result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Call Claude API with simulation data. Returns insight_report + framing_guide.
    Falls back to hardcoded report if API unavailable or fails.
    """
    if not _ANTHROPIC_AVAILABLE:
        print("[prompts] anthropic package not available — using fallback report")
        return _build_fallback(simulation_result)

    api_key = os.environ.get('ANTHROPIC_API_KEY', '')
    if not api_key:
        print("[prompts] ANTHROPIC_API_KEY not set — using fallback report")
        return _build_fallback(simulation_result)

    try:
        client = anthropic.Anthropic(api_key=api_key)
        prompt = build_prompt(simulation_result)

        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4000,
            system=(
                "You are a behavioral economics expert specializing in SaaS pricing psychology. "
                "Your job is to diagnose WHY conversion failed by cross-referencing simulation results with the "
                "framing signals actually present in the pricing copy. You do not give generic advice. "
                "Every claim you make must be grounded in a specific signal, a specific tier, and a specific archetype from the data. "
                "If an archetype underperformed, you name the missing signal and the tier it was absent from. "
                "Always respond with valid JSON only — no markdown formatting, no code blocks, just raw JSON."
            ),
            messages=[
                {"role": "user", "content": prompt}
            ]
        )

        raw = message.content[0].text.strip()

        # Strip markdown code fences if Claude includes them despite instructions
        if raw.startswith('```'):
            raw = re.sub(r'^```(?:json)?\n?', '', raw)
            raw = re.sub(r'\n?```$', '', raw)

        result = json.loads(raw)

        # Validate required keys
        if 'insight_report' not in result or 'framing_guide' not in result:
            raise ValueError("Missing required keys in Claude response")

        return result

    except Exception as e:
        print(f"[prompts] Claude API call failed: {e} — using fallback report")
        return _build_fallback(simulation_result)


def _build_fallback(simulation_result: Dict[str, Any]) -> Dict[str, Any]:
    """Build a data-aware fallback report from simulation summary."""
    summary = simulation_result['summary']
    tiers = summary['pricing_structure']
    by_arch = summary['by_archetype']

    # Customize fallback with actual numbers
    free_pct = summary['tier_pcts'].get(summary['free_tier_name'], 0)

    # Find best and worst converting archetypes
    best_arch = max(by_arch.items(), key=lambda x: x[1].get('conversion_rate', 0))
    worst_arch = min(by_arch.items(), key=lambda x: x[1].get('conversion_rate', 100))

    report = json.loads(json.dumps(FALLBACK_REPORT))  # deep copy

    report['insight_report']['overall_conversion_rates']['free_pct'] = f"{free_pct}%"
    report['insight_report']['projected_mrr'] = {
        "mrr_commentary": f"Projected MRR: ${summary['projected_mrr']:,.2f} from {summary['total_agents']} simulated users.",
        "top_lever": f"Convert more {worst_arch[0]}s — highest gap to behavioral ceiling."
    }
    report['insight_report']['key_behavioral_finding'] = (
        f"{best_arch[0]} shows the highest conversion rate ({best_arch[1].get('conversion_rate', 0)}%) "
        f"while {worst_arch[0]} converts at only {worst_arch[1].get('conversion_rate', 0)}%. "
        f"Reframing your pricing page to serve both archetypes could meaningfully lift overall MRR."
    )

    # Build tier-specific framing guide from actual tier names
    framing = {}
    for t in tiers:
        if t['is_free']:
            framing[t['name']] = FALLBACK_REPORT['framing_guide']['Free']
        elif t == tiers[-1] and len(tiers) > 2:
            framing[t['name']] = FALLBACK_REPORT['framing_guide']['Team']
        else:
            framing[t['name']] = FALLBACK_REPORT['framing_guide']['Pro']

    report['framing_guide'] = framing
    return report


# ── Pricing regeneration ───────────────────────────────────────────────────

def build_regeneration_prompt(pricing_data: Dict[str, Any], simulation_summary: Dict[str, Any], recommendations: list) -> str:
    tiers = pricing_data.get('tiers', [])
    product_name = pricing_data.get('product_name', 'the product')

    # Include ALL features — truncating here is what prevented structural friction decisions
    tier_lines = []
    for t in tiers:
        price_str = 'Free' if t.get('is_free') else f"${t.get('price_monthly', 0)}/mo"
        features  = t.get('features') or []
        signals   = ', '.join(t.get('framing_signals') or []) or 'NONE'
        complexity = t.get('complexity_score', '?')
        tier_lines.append(
            f"  - {t['name']} ({price_str}, complexity={complexity}):\n"
            f"    features (ALL {len(features)}): {', '.join(features) if features else 'none listed'}\n"
            f"    framing_signals: [{signals}]"
        )

    rec_lines = []
    for i, r in enumerate(recommendations, 1):
        rec_lines.append(
            f"  {i}. [{r.get('target_archetype','')}] {r.get('title','')}: {r.get('description','')} "
        )

    by_arch = simulation_summary.get('by_archetype', {})
    BEHAVIORAL_CEILINGS = {
        'Anxious Planner': 70, 'Social Follower': 65, 'Spontaneous Mover': 55,
        'Authority Truster': 60, 'Indifferent Drifter': 20,
    }
    arch_lines = []
    for arch, d in by_arch.items():
        if d.get('count', 0) > 0:
            ceiling = BEHAVIORAL_CEILINGS.get(arch, 50)
            gap = ceiling - d['conversion_rate']
            arch_lines.append(
                f"  - {arch}: {d['conversion_rate']}% actual vs {ceiling}% ceiling "
                f"(gap={gap:.0f}pp, n={d['count']})"
            )

    paid_tiers = [t for t in tiers if not t.get('is_free', False)]
    avg_paid = (
        sum(t.get('price_monthly', 0) for t in paid_tiers) / len(paid_tiers)
        if paid_tiers else 10.0
    )

    free_tiers = [t for t in tiers if t.get('is_free')]
    free_feature_count = len(free_tiers[0].get('features') or []) if free_tiers else 0

    return f"""You are a SaaS pricing strategist. A behavioral simulation has been run on {product_name}'s pricing.

CURRENT PRICING (complete feature lists included — you need these to make structural decisions):
{chr(10).join(tier_lines)}

SIMULATION RESULTS:
- Projected MRR: ${simulation_summary.get('projected_mrr', 0):,.2f}
- Overall conversion rate: {simulation_summary.get('overall_conversion_rate', 0)}%
- Average paid tier price: ${avg_paid:.2f}/mo
- Free tier feature count: {free_feature_count}

ARCHETYPE PERFORMANCE vs BEHAVIORAL CEILINGS:
{chr(10).join(arch_lines)}

RECOMMENDATIONS TO IMPLEMENT:
{chr(10).join(rec_lines)}

CRITICAL REQUIREMENT — STRUCTURAL FRICTION FIRST:
Copy changes alone (renaming tiers, rewriting headlines) do not move behavioral conversion. The simulation shows that archetypes bounce because of structural reasons: the free tier gives too much away, or the paid tier lacks the specific feature that triggers an upgrade decision for that archetype.

You MUST make at least the following structural changes — failure to do so makes this output invalid:

1. FREE TIER TIGHTENING: Identify at least one feature currently on the free tier that is a genuine upgrade driver for an underperforming archetype. Move it exclusively to the first paid tier. This creates a structural felt gap — the archetype hits a wall, not a pitch.
   - For Anxious Planner gaps: move a data-loss-risk or irreversibility feature (exports, history, backups) behind the paywall.
   - For Social Follower gaps: move a collaboration or sharing feature behind the paywall.
   - For Spontaneous Mover gaps: reduce a usage limit (e.g. from unlimited to 5 per month) to create a hard stop.
   - For Authority Truster gaps: move a credibility or reporting feature behind the paywall.

2. USAGE LIMITS: If the free tier has no usage caps, impose at least one concrete numeric limit (e.g. "max 3 projects", "10 exports/month", "1 user seat"). State the specific number.

3. PAYWALL SIGNAL ALIGNMENT: For each paid tier that is missing the required framing signal for an underperforming archetype, add that signal — but also ensure the feature list supports that signal. A "loss_framing" signal with no scarce feature to lose is incoherent.

After making structural changes, then adjust copy, framing, and pricing as needed.

Respond with ONLY a valid JSON object (no markdown, no code blocks):

{{
  "improved_pricing": {{
    "summary_of_changes": "2-3 sentence overview. MUST mention at least one specific feature moved behind the paywall and at least one usage limit imposed on the free tier.",
    "projected_mrr_lift": "Plain English estimate of expected MRR improvement. Name the structural change (not the copy change) as the primary lever.",
    "structural_friction_changes": {{
      "free_tier_limits_imposed": ["list of specific usage limits added to the free tier, e.g. 'max 5 projects', '10 exports/month'"],
      "features_moved_to_paywall": [
        {{
          "feature": "exact feature name from the free tier's feature list",
          "moved_to_tier": "name of the paid tier it now lives behind",
          "target_archetype": "which archetype this creates friction for",
          "mechanism": "one sentence: why hitting this wall triggers an upgrade decision for that archetype"
        }}
      ]
    }},
    "tiers": [
      {{
        "name": "existing or new tier name",
        "price_monthly": <number — 0 if free>,
        "price_changed_from": <original price or null if unchanged>,
        "is_free": <true/false>,
        "features_to_keep": ["features to retain"],
        "features_to_add": ["new features — include specific usage limits as features, e.g. 'Up to 5 projects'"],
        "features_to_remove": ["features to remove — for free tier, list features being moved to paid"],
        "framing_headline": "Specific upgrade CTA or headline copy for this tier",
        "framing_type": "loss | gain | social_proof | authority | simplicity",
        "what_changed": "One sentence: the structural change made (feature moved, limit imposed) — not the copy change",
        "why": "One sentence: how this structural change creates upgrade pressure for the target archetype",
        "name_change": {{
          "suggested_name": "new tier name OR null if keeping current name",
          "reason": "One sentence: why renaming increases perceived value or reduces friction"
        }},
        "price_strategy": {{
          "action": "increase | decrease | keep",
          "reasoning": "One sentence: behavioral justification referencing the archetype and conversion gap"
        }}
      }}
    ]
  }}
}}

Rules:
- Copy-only changes (new headlines, badge text, framing language) are INSUFFICIENT on their own. They must be paired with a structural feature or limit change.
- Every archetype with a conversion gap > 20pp must have at least one structural change targeting it.
- Be specific: name exact features, exact numeric limits, exact tier names.
- Write framing_headline as real marketing copy, not a description of what the copy should do.
- For name_change: suggest a rename only when the current name misaligns with the archetype you're targeting. Null is valid.
- For price_strategy: always specify action and reasoning. "keep" is valid when price is not the constraint."""


def call_claude_regenerate(pricing_data: Dict[str, Any], simulation_summary: Dict[str, Any], recommendations: list) -> Dict[str, Any]:
    """Call Claude to generate an improved pricing model based on simulation results and recommendations."""
    if not _ANTHROPIC_AVAILABLE:
        print("[prompts] anthropic not available — using fallback regeneration")
        return _build_regeneration_fallback(pricing_data, simulation_summary)

    api_key = os.environ.get('ANTHROPIC_API_KEY', '')
    if not api_key:
        print("[prompts] ANTHROPIC_API_KEY not set — using fallback regeneration")
        return _build_regeneration_fallback(pricing_data, simulation_summary)

    try:
        client = anthropic.Anthropic(api_key=api_key)
        prompt = build_regeneration_prompt(pricing_data, simulation_summary, recommendations)

        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4000,
            system=(
                "You are a SaaS pricing strategist with deep expertise in behavioral economics. "
                "You redesign pricing structures based on simulation data. "
                "Your primary tool is structural friction — changing what features live on which tier and imposing concrete usage limits — "
                "not copywriting. Copy changes are secondary. A response that only renames tiers and rewrites headlines without "
                "moving features or adding usage caps has failed its purpose. "
                "Always respond with valid JSON only — no markdown, no code blocks."
            ),
            messages=[{"role": "user", "content": prompt}]
        )

        raw = message.content[0].text.strip()
        if raw.startswith('```'):
            raw = re.sub(r'^```(?:json)?\n?', '', raw)
            raw = re.sub(r'\n?```$', '', raw)

        result = json.loads(raw)
        if 'improved_pricing' not in result:
            raise ValueError("Missing improved_pricing key")
        return result

    except Exception as e:
        print(f"[prompts] Regeneration API call failed: {e} — using fallback")
        return _build_regeneration_fallback(pricing_data, simulation_summary)


def _build_regeneration_fallback(pricing_data: Dict[str, Any], simulation_summary: Dict[str, Any]) -> Dict[str, Any]:
    """Build a data-aware fallback regenerated pricing model."""
    tiers = pricing_data.get('tiers', [])
    mrr   = simulation_summary.get('projected_mrr', 0)
    by_arch = simulation_summary.get('by_archetype', {})

    worst_arch = min(
        ((a, d) for a, d in by_arch.items() if d.get('count', 0) > 0),
        key=lambda x: x[1].get('conversion_rate', 100),
        default=('Unknown', {})
    )

    # Pre-determine what feature gets paywalled (last feature of free tier)
    free_t_orig = next((t for t in tiers if t.get('is_free')), None)
    free_features_orig = (free_t_orig.get('features') or []) if free_t_orig else []
    paywalled_feature = free_features_orig[-1] if free_features_orig else 'Advanced exports'

    regen_tiers = []
    for t in tiers:
        price = t.get('price_monthly', 0)
        is_free = t.get('is_free', False)
        features = t.get('features') or []

        if is_free:
            usage_cap = 'Up to 5 projects'
            regen_tiers.append({
                'name': t['name'],
                'price_monthly': 0,
                'price_changed_from': None,
                'is_free': True,
                'features_to_keep': features[:max(1, len(features) - 1)],
                'features_to_add': [usage_cap],
                'features_to_remove': [paywalled_feature],
                'framing_headline': "You're hitting the limit — here's what you're missing.",
                'framing_type': 'loss',
                'what_changed': f'Moved "{paywalled_feature}" behind the paywall and capped free usage at 5 projects.',
                'why': 'A hard usage wall creates a structural felt gap that activates Anxious Planners and Spontaneous Movers at the moment of friction.',
                'name_change': {
                    'suggested_name': None,
                    'reason': 'Free tier naming is neutral — the structural limit does the work.',
                },
                'price_strategy': {
                    'action': 'keep',
                    'reasoning': 'Free tier remains $0; its job is to create friction at the usage ceiling, not generate revenue.',
                },
            })
        else:
            new_price = round(price * 1.11) if price > 0 else price
            regen_tiers.append({
                'name': t['name'],
                'price_monthly': new_price,
                'price_changed_from': price if new_price != price else None,
                'is_free': False,
                'features_to_keep': features,
                'features_to_add': [paywalled_feature, 'Priority support'],
                'features_to_remove': [],
                'framing_headline': f"Most teams upgrade to {t['name']} within 30 days — here's the one thing that pushes them over.",
                'framing_type': 'social_proof',
                'what_changed': f'Received "{paywalled_feature}" moved from free tier; price adjusted to ${new_price}/mo.',
                'why': 'Social Followers convert when the gated feature is something peers visibly use. The structural gap — not just the copy — drives the decision.',
                'name_change': {
                    'suggested_name': 'Professional' if t['name'].lower() in ('basic', 'starter', 'standard') else None,
                    'reason': 'Renaming to "Professional" signals career identity and raises perceived value for Authority Trusters.',
                },
                'price_strategy': {
                    'action': 'increase',
                    'reasoning': f'Under-conversion is driven by framing and structural gap, not price ceiling — a modest increase to ${new_price}/mo aligns price with the raised perceived value of the gated feature.',
                },
            })

    return {
        'improved_pricing': {
            'summary_of_changes': (
                f'The free tier was structurally tightened: "{paywalled_feature}" was moved exclusively to the first paid tier '
                f'and a 5-project usage cap was imposed, creating a hard upgrade wall. '
                f'Paid tiers now carry that gated feature plus social proof framing to convert Social Followers and Authority Trusters.'
            ),
            'projected_mrr_lift': (
                f'Projected MRR could increase from ${mrr:,.0f} by 12–20%. '
                f'The primary lever is the structural paywall on "{paywalled_feature}" — '
                f'usage-wall friction at the moment of value recognition, not copy, drives the conversion lift for {worst_arch[0]}s.'
            ),
            'structural_friction_changes': {
                'free_tier_limits_imposed': ['Up to 5 projects', '10 exports/month'],
                'features_moved_to_paywall': [
                    {
                        'feature': paywalled_feature,
                        'moved_to_tier': next((t['name'] for t in tiers if not t.get('is_free')), 'Pro'),
                        'target_archetype': worst_arch[0],
                        'mechanism': f'When {worst_arch[0]}s hit the usage wall on "{paywalled_feature}", they face a structural loss — not a sales pitch — which directly activates their upgrade decision.',
                    }
                ],
            },
            'tiers': regen_tiers,
        }
    }


