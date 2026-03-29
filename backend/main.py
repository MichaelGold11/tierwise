import os
import json
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from agents import generate_agents
from simulation import run_simulation
from prompts import call_claude, call_claude_regenerate
from parse_pricing import extract_text, parse_with_claude

app = FastAPI(title="TierWise API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Models ─────────────────────────────────────────────────────────────────

class ParseTextRequest(BaseModel):
    text: str


class SimulateRequest(BaseModel):
    pricing_data: Dict[str, Any]   # structured output from /parse or /parse-text
    agent_count: int = 500


class AnalyzeRequest(BaseModel):
    summary: Dict[str, Any]
    agents: list = []


class RegenerateRequest(BaseModel):
    pricing_data: Dict[str, Any]
    simulation_summary: Dict[str, Any]
    recommendations: list = []


# ── Endpoints ──────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "service": "TierWise API v2"}


@app.post("/parse")
async def parse_file(file: UploadFile = File(...)):
    """
    Accept a file upload (PDF, DOCX, TXT, MD).
    Extract text, then use Claude to parse into structured pricing JSON
    with framing signals, tier data, and behavioral metadata.
    """
    content = await file.read()
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    print(f"\n[TierWise] Parsing file: {file.filename} ({len(content)} bytes)")
    text = extract_text(content, file.filename or 'upload.txt')
    print(f"[TierWise] Extracted {len(text)} characters of text")

    structured = parse_with_claude(text)
    print(f"[TierWise] Parsed {len(structured.get('tiers', []))} tiers via {structured.get('parse_method', 'unknown')}")
    for t in structured.get('tiers', []):
        print(f"  {t['name']}: ${t['price_monthly']}/mo | signals: {t['framing_signals']} | complexity: {t['complexity_score']}")

    return structured


@app.post("/parse-text")
def parse_text(req: ParseTextRequest):
    """
    Accept pasted pricing text (no file upload).
    Uses Claude to parse into structured pricing JSON.
    """
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Text is empty")

    print(f"\n[TierWise] Parsing pasted text ({len(req.text)} chars)")
    structured = parse_with_claude(req.text)
    print(f"[TierWise] Parsed {len(structured.get('tiers', []))} tiers via {structured.get('parse_method', 'unknown')}")

    return structured


@app.post("/simulate")
def simulate(req: SimulateRequest):
    """
    Run behavioral simulation.
    Takes structured pricing_data (from /parse or /parse-text).
    Agents now react to framing_signals extracted from the actual pricing copy.
    """
    agent_count = max(10, min(500, req.agent_count))
    pricing_data = req.pricing_data

    if not pricing_data.get('tiers'):
        raise HTTPException(status_code=400, detail="pricing_data must include at least one tier")

    print(f"\n[TierWise] Generating {agent_count} agents...")
    agents = generate_agents(agent_count)

    # Print first 3 agents
    print(f"\n{'='*60}")
    print(f"FIRST 3 AGENTS")
    print(f"{'='*60}")
    for a in agents[:3]:
        print(f"\nAgent {a['id']} | {a['archetype']}")
        print(f"  Income bracket {a['income_bracket']} → ${a['financial_threshold']}/mo threshold")
        print(f"  loss_aversion={a['loss_aversion']}  neuroticism={a['neuroticism']}")
        print(f"  social_conformity={a['social_conformity']}  authority_trust={a['authority_trust']}")
        print(f"  cognitive_bandwidth={a['cognitive_bandwidth']}  present_bias={a['present_bias']}")
        print(f"  loss_framing_receptivity={a['loss_framing_receptivity']}")
        print(f"  social_proof_receptivity={a['social_proof_receptivity']}")
        print(f"  authority_receptivity={a['authority_receptivity']}")

    print(f"\n[TierWise] Running simulation against {len(pricing_data['tiers'])} tiers...")
    result = run_simulation(agents, pricing_data)

    # Print summary
    summary = result['summary']
    print(f"\n{'='*60}")
    print(f"SIMULATION RESULTS — {summary['total_agents']} agents")
    print(f"{'='*60}")
    for name, pct in summary['tier_pcts'].items():
        print(f"  {name}: {pct}%")
    print(f"\nProjected MRR: ${summary['projected_mrr']:,.2f}")
    print(f"Overall conversion rate: {summary['overall_conversion_rate']}%")
    print(f"\nArchetype breakdown:")
    for arch, data in summary['by_archetype'].items():
        if data['count'] > 0:
            print(f"  {arch}: {data['count']} agents ({data['pct']}%) → {data['conversion_rate']}% converted")
    print(f"\nSignal effectiveness:")
    for signal, eff in summary['signal_effectiveness'].items():
        print(f"  {signal}: +{eff['lift']}% lift (receptive: {eff['receptive_conversion']}% vs non: {eff['non_receptive_conversion']}%)")
    print(f"{'='*60}\n")

    return result


@app.post("/analyze")
def analyze(req: AnalyzeRequest):
    """
    Call Claude API to generate insight report + cognitive framing guide.
    Returns hardcoded fallback if Claude API is unavailable.
    """
    simulation_result = {
        "summary": req.summary,
        "agents": req.agents,
    }
    report = call_claude(simulation_result)
    return report


@app.post("/regenerate")
def regenerate(req: RegenerateRequest):
    """
    Call Claude to generate an improved pricing model based on simulation
    results and the recommendations from /analyze.
    """
    result = call_claude_regenerate(req.pricing_data, req.simulation_summary, req.recommendations)
    print(f"\n[TierWise] Regenerated pricing model with {len(result.get('improved_pricing', {}).get('tiers', []))} tiers")
    return result


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
