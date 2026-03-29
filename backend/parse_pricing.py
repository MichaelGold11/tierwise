"""
parse_pricing.py — Document parsing and pricing structure extraction.

Flow:
  1. extract_text(bytes, filename) → plain text string
  2. parse_with_claude(text) → structured pricing JSON with framing signals

The framing signals extracted here are what makes agents actually react
to pricing copy — not just prices and feature counts.
"""

import os
import re
import json
import io
from typing import Optional

try:
    import anthropic
    _ANTHROPIC_AVAILABLE = True
except ImportError:
    _ANTHROPIC_AVAILABLE = False


# ── Text extraction ────────────────────────────────────────────────────────

def extract_text(file_content: bytes, filename: str) -> str:
    """Extract plain text from uploaded file bytes. Supports PDF, DOCX, TXT, MD."""
    ext = filename.lower().rsplit('.', 1)[-1] if '.' in filename else 'txt'

    if ext in ('txt', 'md', 'csv', 'text'):
        return file_content.decode('utf-8', errors='replace')

    elif ext == 'pdf':
        try:
            import pdfplumber
            with pdfplumber.open(io.BytesIO(file_content)) as pdf:
                pages = [page.extract_text() or '' for page in pdf.pages]
                return '\n\n'.join(p for p in pages if p.strip())
        except ImportError:
            print("[parse_pricing] pdfplumber not installed — falling back to raw decode")
            return file_content.decode('utf-8', errors='replace')
        except Exception as e:
            print(f"[parse_pricing] PDF parse error: {e}")
            return file_content.decode('utf-8', errors='replace')

    elif ext in ('docx', 'doc'):
        try:
            from docx import Document
            doc = Document(io.BytesIO(file_content))
            paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
            return '\n'.join(paragraphs)
        except ImportError:
            print("[parse_pricing] python-docx not installed — falling back to raw decode")
            return file_content.decode('utf-8', errors='replace')
        except Exception as e:
            print(f"[parse_pricing] DOCX parse error: {e}")
            return file_content.decode('utf-8', errors='replace')

    else:
        return file_content.decode('utf-8', errors='replace')


# ── Claude parsing ─────────────────────────────────────────────────────────

PARSE_SYSTEM = (
    "You are a SaaS pricing analyst. Extract structured pricing information from "
    "documents and identify the behavioral framing signals present in the copy. "
    "Respond with valid JSON only — no markdown, no code fences."
)

PARSE_PROMPT = """Parse this pricing document into structured JSON.

PRICING TEXT:
{text}

Return ONLY this JSON structure (no markdown):
{{
  "product_name": "string",
  "billing_options": ["monthly"],
  "tiers": [
    {{
      "name": "tier name",
      "price_monthly": 0.0,
      "price_annual": null,
      "features": ["feature 1", "feature 2"],
      "feature_count": 0,
      "value_proposition": "tagline or short description",
      "target_user": "who this is for",
      "badge": null,
      "highlighted": false,
      "framing_signals": [],
      "complexity_score": 0.3,
      "is_free": false,
      "billing_period": "monthly"
    }}
  ],
  "overall_complexity": 0.4,
  "overall_framing": "gain_framing",
  "has_free_tier": true,
  "has_annual_option": false
}}

FIELD RULES:
- price_monthly: numeric monthly price (0 for free tiers)
- price_annual: price-per-month when billed annually (null if not offered)
- features: list of features/benefits mentioned for this tier
- feature_count: total number of features listed
- value_proposition: the core promise or tagline for this tier (infer from context if not explicit)
- target_user: who this tier is designed for (infer if not stated)
- badge: a label like "Most Popular", "Best Value", "Recommended" — null if none
- highlighted: true if this tier is visually or textually emphasized as the recommended choice
- framing_signals: list of 0-4 psychological signals present IN THIS TIER'S COPY (not inferred):
    "social_proof"   — user counts, testimonials, "most popular", "X teams use this"
    "loss_framing"   — "don't lose", "before it's gone", "you'll miss out", limits that expire
    "authority"      — "recommended by experts", "trusted by [brand]", award badges, certifications
    "scarcity"       — "limited spots", "offer ends", countdown language, "only X left"
    "gain_framing"   — "unlock", "get access to", "grow your", positive future-state language
    "simplicity"     — "easy setup", "no credit card", "one click", "cancel anytime"
- complexity_score: 0.0=very simple (1-3 bullets) to 1.0=overwhelming (20+ features, multiple add-ons)
- overall_complexity: average complexity across all tiers combined
- overall_framing: the dominant framing signal across the whole pricing page

Include ALL tiers found. Sort by price ascending."""


def parse_with_claude(text: str) -> dict:
    """
    Send pricing text to Claude for structured extraction with framing signals.
    Falls back to regex parser if Claude is unavailable.
    """
    api_key = os.environ.get('ANTHROPIC_API_KEY', '')

    if not _ANTHROPIC_AVAILABLE or not api_key:
        print("[parse_pricing] Claude unavailable — using regex fallback")
        return _fallback_parse(text)

    try:
        client = anthropic.Anthropic(api_key=api_key)
        prompt = PARSE_PROMPT.format(text=text[:10000])

        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2500,
            system=PARSE_SYSTEM,
            messages=[{"role": "user", "content": prompt}]
        )

        raw = message.content[0].text.strip()
        # Strip markdown code fences if Claude adds them despite instructions
        raw = re.sub(r'^```(?:json)?\n?', '', raw)
        raw = re.sub(r'\n?```\s*$', '', raw.strip())

        result = json.loads(raw)
        result['raw_text_length'] = len(text)
        result['parse_method'] = 'claude'
        return _normalize(result)

    except json.JSONDecodeError as e:
        print(f"[parse_pricing] JSON parse error: {e} — using regex fallback")
        return _fallback_parse(text)
    except Exception as e:
        print(f"[parse_pricing] Claude parse error: {e} — using regex fallback")
        return _fallback_parse(text)


# ── Normalization ──────────────────────────────────────────────────────────

def _normalize(data: dict) -> dict:
    """Ensure all required fields exist with correct types."""
    data.setdefault('product_name', 'Your Product')
    data.setdefault('billing_options', ['monthly'])
    data.setdefault('tiers', [])
    data.setdefault('overall_complexity', 0.4)
    data.setdefault('overall_framing', 'gain_framing')
    data.setdefault('has_free_tier', False)
    data.setdefault('has_annual_option', False)
    data.setdefault('parse_method', 'claude')
    data.setdefault('raw_text_length', 0)

    valid_signals = {'social_proof', 'loss_framing', 'authority', 'scarcity', 'gain_framing', 'simplicity'}

    for tier in data['tiers']:
        tier.setdefault('price_monthly', 0.0)
        tier.setdefault('price_annual', None)
        tier.setdefault('features', [])
        tier.setdefault('feature_count', len(tier.get('features', [])))
        tier.setdefault('value_proposition', '')
        tier.setdefault('target_user', '')
        tier.setdefault('badge', None)
        tier.setdefault('highlighted', False)
        tier.setdefault('framing_signals', [])
        tier.setdefault('complexity_score', 0.3)
        tier.setdefault('billing_period', 'monthly')

        # Type coercion
        try:
            tier['price_monthly'] = float(tier['price_monthly'])
        except (TypeError, ValueError):
            tier['price_monthly'] = 0.0

        if tier.get('price_annual') is not None:
            try:
                tier['price_annual'] = float(tier['price_annual'])
            except (TypeError, ValueError):
                tier['price_annual'] = None

        tier['is_free'] = tier['price_monthly'] == 0.0

        # Filter framing signals to known valid values
        tier['framing_signals'] = [s for s in tier['framing_signals'] if s in valid_signals]

        # Ensure feature_count matches features list
        if not tier['feature_count'] and tier['features']:
            tier['feature_count'] = len(tier['features'])

    # Sort tiers by price
    data['tiers'].sort(key=lambda t: t['price_monthly'])
    data['has_free_tier'] = any(t['is_free'] for t in data['tiers'])
    data['has_annual_option'] = any(t.get('price_annual') is not None for t in data['tiers'])

    return data


# ── Regex fallback ─────────────────────────────────────────────────────────

# Words that look like tier names but are actually labels/section headings
_SKIP_NAMES = {
    'note', 'includes', 'features', 'add', 'all', 'the', 'plan', 'plans',
    'pricing', 'billing', 'upgrade', 'contact', 'support', 'compare',
    'overview', 'details', 'summary', 'faq', 'more', 'see', 'get',
}

def _make_tier(name: str, price: float, price_annual: Optional[float],
               features: list, badge: Optional[str] = None) -> dict:
    return {
        'name': name,
        'price_monthly': price,
        'price_annual': price_annual,
        'features': features,
        'feature_count': len(features),
        'value_proposition': '',
        'target_user': '',
        'badge': badge,
        'highlighted': badge is not None,
        'framing_signals': [],
        'complexity_score': min(0.9, 0.15 + len(features) * 0.04),
        'is_free': price == 0.0,
        'billing_period': 'monthly',
    }


def _extract_price(text: str) -> Optional[float]:
    """Return first dollar-sign price found in text, or None."""
    m = re.search(r'\$\s*(\d+(?:\.\d+)?)', text)
    if m:
        return float(m.group(1))
    # Handle "free" / "$0" keywords
    if re.search(r'\bfree\b', text, re.IGNORECASE):
        return 0.0
    return None


def _extract_annual(text: str) -> Optional[float]:
    m = re.search(r'annual.*?\$\s*(\d+(?:\.\d+)?)', text, re.IGNORECASE)
    return float(m.group(1)) if m else None


def _extract_badge(lines_around: list) -> Optional[str]:
    badge_pattern = re.compile(
        r'\b(most\s+popular|best\s+value|recommended|most\s+loved|top\s+pick|'
        r'popular|featured|best\s+deal|best\s+choice)\b', re.IGNORECASE
    )
    for line in lines_around:
        m = badge_pattern.search(line)
        if m:
            return m.group(0).title()
    return None


def _is_feature_line(line: str) -> bool:
    """True if line looks like a bullet-point feature."""
    return bool(re.match(r'^[\-\*\•\✓\✗\+►▸→]\s+\S', line) or
                re.match(r'^\s{2,}[\-\*\•\✓\+►▸→]\s+\S', line) or
                re.match(r'^\s{2,}\S', line))


def _fallback_parse(text: str) -> dict:
    """
    Multi-strategy regex parser for when Claude is unavailable.
    Tries three strategies in order, merges results, removes duplicates.
    Cannot extract framing signals (requires Claude).
    """
    lines = text.splitlines()
    stripped = [l.strip() for l in lines]
    tiers: list = []
    seen_names: set = set()

    def _add(tier: dict):
        key = tier['name'].lower()
        if key not in seen_names:
            seen_names.add(key)
            tiers.append(tier)

    # ── Strategy 1: "Name: $price" or "Name - $price" on one line ────────
    for i, line in enumerate(stripped):
        m = re.match(
            r'^([A-Za-z][A-Za-z0-9\s]{1,30}?)\s*(?:[:\-–—])\s*(.*)',
            line
        )
        if not m:
            continue
        name = m.group(1).strip()
        rest = m.group(2)
        if name.lower() in _SKIP_NAMES or len(name) < 2:
            continue

        price = _extract_price(rest + ' ' + line)
        if price is None:
            # Price might be on the very next line
            if i + 1 < len(stripped):
                price = _extract_price(stripped[i + 1])
        if price is None:
            continue

        annual = _extract_annual(rest)
        # Collect features: lines below that look like bullets, until next potential tier
        features = []
        j = i + 1
        while j < len(stripped) and j < i + 20:
            if _is_feature_line(stripped[j]):
                feat = re.sub(r'^[\-\*\•\✓\✗\+►▸→\s]+', '', stripped[j]).strip()
                if feat:
                    features.append(feat)
            elif stripped[j] and re.match(r'^[A-Za-z][A-Za-z0-9\s]{1,30}?\s*[:\-–—]', stripped[j]):
                break
            j += 1

        badge = _extract_badge(stripped[max(0, i-1):i+4])
        _add(_make_tier(name, price, annual, features, badge))

    # ── Strategy 2: Header block (tier name alone on a line, price nearby) ─
    if len(tiers) < 1:
        i = 0
        while i < len(stripped):
            line = stripped[i]
            # Candidate header: short, starts with capital, no digits, no punctuation (except space)
            if (re.match(r'^[A-Z][A-Za-z\s]{1,25}$', line) and
                    line.lower() not in _SKIP_NAMES and
                    len(line.split()) <= 4):
                name = line.strip()
                # Search next 4 lines for a price
                price = None
                annual = None
                for k in range(i + 1, min(i + 5, len(stripped))):
                    p = _extract_price(stripped[k])
                    if p is not None:
                        price = p
                        annual = _extract_annual(stripped[k])
                        break
                if price is not None:
                    # Collect feature lines
                    features = []
                    j = i + 1
                    while j < len(stripped) and j < i + 25:
                        if _is_feature_line(stripped[j]):
                            feat = re.sub(r'^[\-\*\•\✓\✗\+►▸→\s]+', '', stripped[j]).strip()
                            if feat:
                                features.append(feat)
                        elif stripped[j] and re.match(r'^[A-Z][A-Za-z\s]{1,25}$', stripped[j]):
                            break
                        j += 1
                    badge = _extract_badge(stripped[i:i+5])
                    _add(_make_tier(name, price, annual, features, badge))
            i += 1

    # ── Strategy 3: Scan all lines for price occurrences, backtrack for name ─
    if len(tiers) < 1:
        for i, line in enumerate(stripped):
            price = _extract_price(line)
            if price is None:
                continue
            # Look back up to 3 lines for a name
            for k in range(i, max(-1, i - 4), -1):
                candidate = re.match(r'^([A-Z][A-Za-z0-9\s]{1,30}?)[\s\:\-–—]*$', stripped[k])
                if candidate:
                    name = candidate.group(1).strip()
                    if name.lower() not in _SKIP_NAMES and len(name) >= 2:
                        annual = _extract_annual(line)
                        badge = _extract_badge(stripped[max(0, i-1):i+3])
                        _add(_make_tier(name, price, annual, [], badge))
                        break

    tiers.sort(key=lambda t: t['price_monthly'])

    # Last resort: single unknown tier so simulation can still run
    if not tiers:
        print("[parse_pricing] regex fallback: could not parse any tiers from text")
        tiers = [{
            'name': 'Unknown Tier',
            'price_monthly': 0.0,
            'price_annual': None,
            'features': [],
            'feature_count': 0,
            'value_proposition': 'Could not parse pricing — check text format',
            'target_user': '',
            'badge': None,
            'highlighted': False,
            'framing_signals': [],
            'complexity_score': 0.3,
            'is_free': True,
            'billing_period': 'monthly',
        }]

    return {
        'product_name': 'Your Product',
        'billing_options': ['monthly'],
        'tiers': tiers,
        'overall_complexity': round(sum(t['complexity_score'] for t in tiers) / len(tiers), 2),
        'overall_framing': 'gain_framing',
        'has_free_tier': any(t['is_free'] for t in tiers),
        'has_annual_option': any(t.get('price_annual') is not None for t in tiers),
        'raw_text_length': len(text),
        'parse_method': 'regex_fallback',
    }
