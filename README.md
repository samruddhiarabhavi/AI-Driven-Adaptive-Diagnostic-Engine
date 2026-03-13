# AdaptIQ — AI-Driven Adaptive Diagnostic Engine

> IRT-powered adaptive testing + Anthropic Claude study plans. 3 files. Zero config hell.

```
adaptive-engine/
├── database.py       # MongoDB connection + 25 GRE question seed data
├── backend.py        # FastAPI app: IRT algorithm + AI insights + all routes
├── frontend.html     # Single-page UI — open in any browser
├── requirements.txt
└── .env.example
```

---

## Quickstart

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure environment
```bash
cp .env.example .env
# Edit .env — set MONGODB_URI and ANTHROPIC_API_KEY
```

### 3. Run the backend
```bash
uvicorn backend:app --reload
```
Questions are auto-seeded on first startup. No separate seed step needed.

### 4. Open the frontend
```
Open frontend.html in your browser (double-click or open with Live Server)
```

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Service status + question count |
| `POST` | `/sessions/start` | Start a new adaptive session |
| `GET` | `/questions/next/{session_id}` | Get next adaptively selected question |
| `POST` | `/sessions/submit` | Submit an answer, update ability |
| `GET` | `/sessions/{session_id}` | Full session summary + AI study plan |

Interactive docs: **http://localhost:8000/docs**

---

## Adaptive Algorithm

The engine uses the **1-Parameter Logistic (Rasch) IRT model**.

**Probability of correct response:**
```
P(θ, b) = 1 / (1 + exp(-(θ - b)))
```
- `θ` = student ability estimate (logit scale, starts at 0.0)
- `b` = item difficulty (mapped from [0.1, 1.0] → [-2.4, +3.0] logit)

**Ability update after each response (online Newton-Raphson):**
```
Δθ = lr × (response - P) / P(1-P)
θ_new = clamp(θ + Δθ, -4, +4)
```
- Correct answer → `response = 1` → θ increases
- Wrong answer → `response = 0` → θ decreases
- The denominator `P(1-P)` is Fisher Information — updates are *larger* near 50% difficulty and smaller at extremes (correctly uncertain about ability evidence)

**Question selection — Maximum Fisher Information (MFI):**
```
I(θ) = P(θ, b) × (1 - P(θ, b))
```
Each question is scored by the information it would yield at the current θ. The unseen question with the highest Fisher Information is selected — which in the 1PL model means choosing the item whose difficulty logit is closest to θ (targeting 50% success probability per attempt).

---

## AI Study Plan

Once 10 questions are answered, session performance data is sent to **Claude Sonnet** via the Anthropic API:
- Topics attempted + per-topic accuracy
- Final ability estimate θ with descriptive level label
- Weak topics (accuracy < 60%)

Claude returns a structured **3-Step Study Plan** with a single "Quick Win" action for the week.

---

## AI Log (How AI Tools Were Used)

**Speed-ups:**
- Claude generated the 25 GRE seed questions with metadata in one prompt
- Claude helped structure the IRT Newton-Raphson update with proper numerical stability (clamping Fisher Information variance to avoid division by zero)
- Frontend CSS layout and option button states were drafted rapidly with AI assistance

**What AI couldn't solve:**
- The IRT ability clamping bounds [-4, +4] required manual tuning — AI initially suggested wider bounds that caused instability in ability estimates after a single very easy/hard question with high learning rate
- MongoDB Motor async context in FastAPI lifespan required manual debugging; AI-generated code used deprecated `startup`/`shutdown` event handlers

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MONGODB_URI` | `mongodb://localhost:27017` | MongoDB connection string |
| `DATABASE_NAME` | `adaptive_engine` | Database name |
| `ANTHROPIC_API_KEY` | *(required for AI plan)* | Your Anthropic API key |
| `MAX_QUESTIONS_PER_SESSION` | `10` | Questions before session ends |
| `BASELINE_ABILITY` | `0.0` | Starting θ in logit scale |
| `LEARNING_RATE` | `0.5` | IRT update step size |
"# AI-Driven-Adaptive-Diagnostic-Engine" 
