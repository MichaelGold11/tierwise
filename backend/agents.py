import random
import json
import os

# Load demographics data
_data_dir = os.path.join(os.path.dirname(__file__), '..', 'data')

with open(os.path.join(_data_dir, 'demographics.json')) as f:
    DEMOGRAPHICS = json.load(f)

INCOME_TO_THRESHOLD = {int(k): v for k, v in DEMOGRAPHICS['income_bracket_to_threshold'].items()}
WTP_TO_AMOUNT = {int(k): v for k, v in DEMOGRAPHICS['wtp_ceiling_bracket_to_amount'].items()}

# Survey answer weights (realistic population distributions)
Q3_W = DEMOGRAPHICS['q3_weights']
Q4_W = DEMOGRAPHICS['q4_weights']
Q5_W = DEMOGRAPHICS['q5_weights']
Q6_W = DEMOGRAPHICS['q6_weights']
Q7_W = DEMOGRAPHICS['q7_weights']
Q8_W = DEMOGRAPHICS['q8_weights']
Q9_W = DEMOGRAPHICS['q9_weights']
Q10_W = DEMOGRAPHICS['q10_weights']


def _weighted_choice(weights: dict) -> str:
    keys = list(weights.keys())
    values = list(weights.values())
    return random.choices(keys, weights=values, k=1)[0]


def _clamp(val: float, lo=0.0, hi=1.0) -> float:
    return max(lo, min(hi, val))


def _score_q3(answer: str) -> dict:
    mapping = {
        'A': {'loss_aversion': 0.85, 'scarcity_sensitivity': 0.85},
        'B': {'loss_aversion': 0.55, 'scarcity_sensitivity': 0.50},
        'C': {'loss_aversion': 0.25, 'scarcity_sensitivity': 0.30},
        'D': {'loss_aversion': 0.10, 'scarcity_sensitivity': 0.10},
    }
    return mapping[answer]


def _score_q4(answer: str) -> dict:
    mapping = {
        'A': {'social_conformity': 0.90, 'authority_trust': 0.70},
        'B': {'social_conformity': 0.55, 'authority_trust': 0.50},
        'C': {'social_conformity': 0.20, 'authority_trust': 0.25},
        'D': {'social_conformity': 0.05, 'authority_trust': 0.10},
    }
    return mapping[answer]


def _score_q5(answer: str) -> dict:
    mapping = {
        'A': {'cognitive_bandwidth': 0.90},
        'B': {'cognitive_bandwidth': 0.25},
        'C': {'cognitive_bandwidth': 0.20},
        'D': {'cognitive_bandwidth': 0.05},
    }
    return mapping[answer]


def _score_q6(answer: str) -> dict:
    mapping = {
        'A': {'default_stickiness': 0.10, 'price_sensitivity': 0.90},
        'B': {'default_stickiness': 0.85, 'price_sensitivity': 0.20},
        'C': {'default_stickiness': 0.50, 'price_sensitivity': 0.70},
        'D': {'default_stickiness': 0.80, 'price_sensitivity': 0.15},
    }
    return mapping[answer]


def _score_q7(answer: str) -> dict:
    mapping = {
        'A': {'present_bias': 0.10, 'loss_aversion_boost': 0.10},
        'B': {'present_bias': 0.40, 'loss_aversion_boost': 0.0},
        'C': {'present_bias': 0.85, 'loss_aversion_boost': 0.0},
        'D': {'present_bias': 0.70, 'loss_aversion_boost': 0.0},
    }
    return mapping[answer]


def _score_q8(answer: str) -> dict:
    mapping = {
        'A': {'conscientiousness': 0.90, 'openness': 0.40},
        'B': {'conscientiousness': 0.45, 'openness': 0.55},
        'C': {'conscientiousness': 0.25, 'openness': 0.85},
        'D': {'conscientiousness': 0.60, 'openness': 0.35},
    }
    return mapping[answer]


def _score_q9(answer: str) -> dict:
    mapping = {
        'A': {'authority_trust': 0.90, 'social_conformity_boost': 0.05, 'openness_boost': 0.0, 'neuroticism_boost': 0.0},
        'B': {'authority_trust': 0.45, 'social_conformity_boost': 0.20, 'openness_boost': 0.0, 'neuroticism_boost': 0.0},
        'C': {'authority_trust': 0.20, 'social_conformity_boost': 0.0, 'openness_boost': 0.15, 'neuroticism_boost': 0.0},
        'D': {'authority_trust': 0.35, 'social_conformity_boost': 0.0, 'openness_boost': 0.0, 'neuroticism_boost': 0.15},
    }
    return mapping[answer]


def _score_q10(answer: str) -> dict:
    mapping = {
        'A': {'neuroticism': 0.85, 'loss_aversion_boost': 0.10, 'price_sensitivity_boost': 0.0, 'openness_boost': 0.0},
        'B': {'neuroticism': 0.15, 'loss_aversion_boost': 0.0, 'price_sensitivity_boost': 0.0, 'openness_boost': 0.0},
        'C': {'neuroticism': 0.45, 'loss_aversion_boost': 0.0, 'price_sensitivity_boost': 0.10, 'openness_boost': 0.0},
        'D': {'neuroticism': 0.30, 'loss_aversion_boost': 0.0, 'price_sensitivity_boost': 0.0, 'openness_boost': 0.10},
    }
    return mapping[answer]


def _classify_archetype(attrs: dict) -> str:
    """
    Classify into one of 5 archetypes using priority ordering.
    Thresholds are calibrated to the actual score distributions
    produced by the weighted-average attribute formulas (typical range 0.25–0.70).
    """
    la  = attrs['loss_aversion']
    n   = attrs['neuroticism']
    sc  = attrs['social_conformity']
    at  = attrs['authority_trust']
    con = attrs['conscientiousness']
    pb  = attrs['present_bias']
    op  = attrs['openness']
    ds  = attrs.get('default_stickiness', 0.5)

    # Anxious Planner: high loss aversion + elevated neuroticism
    if la >= 0.58 and n >= 0.52:
        return 'Anxious Planner'

    # Authority Truster: high authority trust + conscientious
    if at >= 0.58 and con >= 0.55:
        return 'Authority Truster'

    # Social Follower: high social conformity
    if sc >= 0.55:
        return 'Social Follower'

    # Spontaneous Mover: high present bias + openness
    if pb >= 0.58 and op >= 0.50:
        return 'Spontaneous Mover'

    # Indifferent Drifter: fallback (low engagement across the board)
    return 'Indifferent Drifter'


def generate_agents(n: int = 500) -> list:
    agents = []

    # Income bracket distribution weights (brackets 1-7)
    income_weights = DEMOGRAPHICS['income_bracket_weights']

    for i in range(n):
        # Q1: Income bracket
        income_bracket = random.choices(range(1, 8), weights=income_weights, k=1)[0]
        financial_threshold = INCOME_TO_THRESHOLD[income_bracket]

        # Q2: WTP ceiling bracket
        wtp_bracket = random.choices(range(0, 6), weights=[0.10, 0.20, 0.25, 0.25, 0.12, 0.08], k=1)[0]
        wtp_ceiling = WTP_TO_AMOUNT[wtp_bracket]

        # Q3 scoring
        q3 = _weighted_choice(Q3_W)
        q3_scores = _score_q3(q3)

        # Q4 scoring
        q4 = _weighted_choice(Q4_W)
        q4_scores = _score_q4(q4)

        # Q5 scoring
        q5 = _weighted_choice(Q5_W)
        q5_scores = _score_q5(q5)

        # Q6 scoring
        q6 = _weighted_choice(Q6_W)
        q6_scores = _score_q6(q6)

        # Q7 scoring
        q7 = _weighted_choice(Q7_W)
        q7_scores = _score_q7(q7)

        # Q8 scoring
        q8 = _weighted_choice(Q8_W)
        q8_scores = _score_q8(q8)

        # Q9 scoring
        q9 = _weighted_choice(Q9_W)
        q9_scores = _score_q9(q9)

        # Q10 scoring
        q10 = _weighted_choice(Q10_W)
        q10_scores = _score_q10(q10)

        # --- Compute 16 core attributes ---

        # loss_aversion: Q3 x 0.5 + Q7 base + boosts, clamped
        loss_aversion = _clamp(
            q3_scores['loss_aversion'] * 0.5
            + (1 - q7_scores['present_bias']) * 0.3  # higher present_bias = lower loss aversion
            + q7_scores.get('loss_aversion_boost', 0.0)
            + q10_scores.get('loss_aversion_boost', 0.0)
            + random.gauss(0, 0.04)
        )

        # scarcity_sensitivity: primarily from Q3
        scarcity_sensitivity = _clamp(
            q3_scores['scarcity_sensitivity'] * 0.7
            + (loss_aversion * 0.3)
            + random.gauss(0, 0.04)
        )

        # social_conformity: Q4 + Q9 weighted
        social_conformity = _clamp(
            q4_scores['social_conformity'] * 0.6
            + q9_scores.get('social_conformity_boost', 0.0)
            + random.gauss(0, 0.05)
        )

        # authority_trust: Q4 + Q9 + Q8 weighted
        authority_trust = _clamp(
            q4_scores['authority_trust'] * 0.35
            + q9_scores['authority_trust'] * 0.45
            + q8_scores['conscientiousness'] * 0.10  # conscientious people tend to trust authority
            + q9_scores.get('social_conformity_boost', 0.0) * 0.10
            + random.gauss(0, 0.04)
        )

        # cognitive_bandwidth: Q5 direct
        cognitive_bandwidth = _clamp(q5_scores['cognitive_bandwidth'] + random.gauss(0, 0.05))

        # default_stickiness: Q6 direct
        default_stickiness = _clamp(q6_scores['default_stickiness'] + random.gauss(0, 0.04))

        # price_sensitivity: Q6 + Q10 boost
        price_sensitivity = _clamp(
            q6_scores['price_sensitivity']
            + q10_scores.get('price_sensitivity_boost', 0.0)
            + random.gauss(0, 0.04)
        )

        # present_bias: Q7 direct
        present_bias = _clamp(q7_scores['present_bias'] + random.gauss(0, 0.04))

        # conscientiousness: Q8 direct
        conscientiousness = _clamp(q8_scores['conscientiousness'] + random.gauss(0, 0.04))

        # openness: Q8 base + Q9 boost + Q10 boost
        openness = _clamp(
            q8_scores['openness'] * 0.65
            + q9_scores.get('openness_boost', 0.0)
            + q10_scores.get('openness_boost', 0.0)
            + random.gauss(0, 0.04)
        )

        # neuroticism: Q10 direct + Q9 boost
        neuroticism = _clamp(
            q10_scores['neuroticism'] * 0.80
            + q9_scores.get('neuroticism_boost', 0.0)
            + random.gauss(0, 0.04)
        )

        # Derived: agreeableness and extraversion (not directly from survey but needed for nudge scores)
        # agreeableness correlates with social_conformity and low neuroticism
        agreeableness = _clamp(
            social_conformity * 0.4
            + (1 - neuroticism) * 0.3
            + conscientiousness * 0.2
            + random.gauss(0, 0.06)
        )

        # extraversion correlates with openness and low conscientiousness
        extraversion = _clamp(
            openness * 0.35
            + (1 - present_bias) * 0.25
            + social_conformity * 0.25
            + random.gauss(0, 0.06)
        )

        # --- Nudge receptivity scores ---
        social_proof_receptivity = _clamp(
            (social_conformity * 0.5)
            + (agreeableness * 0.3)
            + (openness * 0.2)
        )

        loss_framing_receptivity = _clamp(
            (loss_aversion * 0.6)
            + (neuroticism * 0.25)
            + (scarcity_sensitivity * 0.15)
        )

        authority_receptivity = _clamp(
            (authority_trust * 0.6)
            + (conscientiousness * 0.4)
        )

        complexity_tolerance = _clamp(
            (cognitive_bandwidth * 0.6)
            + (conscientiousness * 0.4)
        )

        # Assemble attribute dict for archetype classification
        attrs = {
            'loss_aversion': loss_aversion,
            'neuroticism': neuroticism,
            'social_conformity': social_conformity,
            'authority_trust': authority_trust,
            'conscientiousness': conscientiousness,
            'present_bias': present_bias,
            'openness': openness,
        }

        archetype = _classify_archetype(attrs)

        agent = {
            'id': i,
            # Financial
            'income_bracket': income_bracket,
            'financial_threshold': financial_threshold,
            'wtp_ceiling': wtp_ceiling,
            # Core 16 attributes
            'loss_aversion': round(loss_aversion, 3),
            'scarcity_sensitivity': round(scarcity_sensitivity, 3),
            'social_conformity': round(social_conformity, 3),
            'authority_trust': round(authority_trust, 3),
            'cognitive_bandwidth': round(cognitive_bandwidth, 3),
            'default_stickiness': round(default_stickiness, 3),
            'price_sensitivity': round(price_sensitivity, 3),
            'present_bias': round(present_bias, 3),
            'conscientiousness': round(conscientiousness, 3),
            'openness': round(openness, 3),
            'neuroticism': round(neuroticism, 3),
            'agreeableness': round(agreeableness, 3),
            'extraversion': round(extraversion, 3),
            # Nudge receptivity
            'social_proof_receptivity': round(social_proof_receptivity, 3),
            'loss_framing_receptivity': round(loss_framing_receptivity, 3),
            'authority_receptivity': round(authority_receptivity, 3),
            'complexity_tolerance': round(complexity_tolerance, 3),
            # Classification
            'archetype': archetype,
            # Survey answers (for audit)
            'survey': {'q3': q3, 'q4': q4, 'q5': q5, 'q6': q6, 'q7': q7, 'q8': q8, 'q9': q9, 'q10': q10},
            # Decision fields (filled by simulation)
            'chosen_tier': None,
            'decision_probability': None,
            'actual_decision': None,
            'decision_reason': None,
        }

        agents.append(agent)

    return agents


if __name__ == '__main__':
    agents = generate_agents(500)
    print("\n=== FIRST 3 AGENTS ===")
    for a in agents[:3]:
        print(f"\nAgent {a['id']} | Archetype: {a['archetype']}")
        print(f"  Income bracket: {a['income_bracket']} → threshold: ${a['financial_threshold']}/mo")
        print(f"  loss_aversion={a['loss_aversion']}  neuroticism={a['neuroticism']}")
        print(f"  social_conformity={a['social_conformity']}  authority_trust={a['authority_trust']}")
        print(f"  cognitive_bandwidth={a['cognitive_bandwidth']}  present_bias={a['present_bias']}")
        print(f"  conscientiousness={a['conscientiousness']}  openness={a['openness']}")
        print(f"  default_stickiness={a['default_stickiness']}  price_sensitivity={a['price_sensitivity']}")
        print(f"  loss_framing_receptivity={a['loss_framing_receptivity']}")
        print(f"  social_proof_receptivity={a['social_proof_receptivity']}")
        print(f"  authority_receptivity={a['authority_receptivity']}")
        print(f"  complexity_tolerance={a['complexity_tolerance']}")
        print(f"  Survey: {a['survey']}")

    archetype_counts = {}
    for a in agents:
        archetype_counts[a['archetype']] = archetype_counts.get(a['archetype'], 0) + 1
    print("\n=== ARCHETYPE DISTRIBUTION ===")
    for k, v in sorted(archetype_counts.items()):
        print(f"  {k}: {v} ({v/5:.1f}%)")
