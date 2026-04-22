# TierWise — Behavioral Pricing Intelligence

TierWise generates 500 AI agents with unique financial attributes 
and behavioral economics profiles, runs them through your SaaS 
pricing structure, and produces a cognitive framing guide showing 
exactly how to rewrite each tier to maximize conversion.

## The Problem
73% of AI companies are still guessing at their pricing model. 
94.5% of ChatGPT users never pay. Freemium converts at 2-5% 
industry wide. Companies are making million-dollar pricing 
decisions blind.

## What TierWise Does
1. Upload your pricing structure
2. 500 behaviorally-modeled agents simulate subscription decisions
3. See which cognitive types converted and which didn't
4. Get a Claude-generated insight report and cognitive framing guide

## Five Agent Archetypes
- Anxious Planner (22%) — high loss aversion
- Social Follower (28%) — high social conformity
- Spontaneous Mover (20%) — high present bias
- Authority Truster (18%) — high authority trust
- Indifferent Drifter (12%) — low motivation across all signals

## Behavioral Economics Framework
Built on Prospect Theory (Kahneman & Tversky), Temporal Discounting 
(Laibson), Social Proof (Cialdini), Cognitive Load Theory (Sweller), 
and Authority Bias (Milgram).

## Tech Stack
- Backend: Python, FastAPI, Anthropic Claude API
- Frontend: Vanilla HTML, CSS, JavaScript, HTML5 Canvas

## How to Run
1. Clone the repository
2. Install dependencies: pip install -r backend/requirements.txt
3. Create backend/.env with your key: ANTHROPIC_API_KEY=your-key
4. Start backend: cd backend && uvicorn main:app --reload
5. Open frontend/index.html in your browser

## Hackathon
Built for the behavioral economics AI hackathon. 
Prompt: "Create a system that reshapes information to match 
a user's unique cognitive style and sensory preferences."
