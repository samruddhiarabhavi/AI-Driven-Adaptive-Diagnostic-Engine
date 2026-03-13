"""
backend.py — Adaptive Diagnostic Engine API
============================================
All-in-one FastAPI backend containing:
  - IRT (Rasch model) adaptive algorithm
  - Anthropic AI study plan generation
  - All API endpoints

Run:  uvicorn backend:app --reload

Endpoints:
  POST /sessions/start          → start a new session
  GET  /questions/next/{sid}    → get next adaptive question
  POST /sessions/submit         → submit an answer
  GET  /sessions/{sid}          → get full session summary + study plan
  GET  /health                  → service health check
"""

import math
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import anthropic
from bson import ObjectId
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from database import connect_db, close_db, get_db, seed_questions

load_dotenv()

ANTHROPIC_API_KEY       = os.getenv("ANTHROPIC_API_KEY", "")
MAX_QUESTIONS           = int(os.getenv("MAX_QUESTIONS_PER_SESSION", 10))
BASELINE_ABILITY        = float(os.getenv("BASELINE_ABILITY", 0.0))
LEARNING_RATE           = float(os.getenv("LEARNING_RATE", 0.5))


# ══════════════════════════════════════════════════════════════════════════════
# IRT ADAPTIVE ALGORITHM  (1-Parameter Logistic / Rasch Model)
# ══════════════════════════════════════════════════════════════════════════════
#
#  Core equation — probability of correct response:
#      P(θ, b) = 1 / (1 + exp(-(θ - b)))
#
#  θ  = student ability  (logit scale, starts at 0.0)
#  b  = item difficulty  (mapped from [0.1, 1.0] → [-2.4, +3.0] logit)
#
#  Ability update (online Newton-Raphson step):
#      Δθ = lr × (response − P) / P(1−P)
#      θ_new = clamp(θ + Δθ, -4, +4)
#
#  Question selection — Maximum Fisher Information (MFI):
#      I(θ) = P(θ,b) × (1 − P(θ,b))
#      Pick the unseen question that maximises I(θ)
#      ↳ equivalent to choosing b closest to θ (50% success probability)
# ══════════════════════════════════════════════════════════════════════════════

def difficulty_to_logit(d: float) -> float:
    """Map difficulty [0.1, 1.0] → logit scale [-2.4, +3.0]."""
    return (d - 0.5) * 6.0


def p_correct(theta: float, b: float) -> float:
    """1PL IRT probability of a correct response."""
    try:
        return 1.0 / (1.0 + math.exp(-(theta - b)))
    except OverflowError:
        return 0.0 if theta < b else 1.0


def update_ability(theta: float, b: float, is_correct: bool) -> float:
    """Online Newton-Raphson ability update. Clamped to [-4, +4]."""
    p = p_correct(theta, b)
    variance = max(p * (1.0 - p), 1e-6)          # Fisher Information = P(1-P)
    response  = 1.0 if is_correct else 0.0
    delta     = LEARNING_RATE * (response - p) / variance
    return max(-4.0, min(4.0, theta + delta))


def select_next_question(theta: float, candidates: list[dict], seen_ids: list[str]) -> dict | None:
    """Pick the unseen question maximising Fisher Information at current θ."""
    unseen = [q for q in candidates if str(q["_id"]) not in seen_ids]
    if not unseen:
        return None
    return max(unseen, key=lambda q: p_correct(theta, difficulty_to_logit(q["difficulty"])) *
                                     (1 - p_correct(theta, difficulty_to_logit(q["difficulty"]))))


# ══════════════════════════════════════════════════════════════════════════════
# AI STUDY PLAN  (Anthropic Claude)
# ══════════════════════════════════════════════════════════════════════════════

def _build_prompt(student_id: str, theta: float, responses: list[dict]) -> str:
    # Aggregate per-topic stats
    topic_stats: dict[str, dict] = {}
    for r in responses:
        t = r["topic"]
        if t not in topic_stats:
            topic_stats[t] = {"correct": 0, "total": 0}
        topic_stats[t]["total"] += 1
        if r["is_correct"]:
            topic_stats[t]["correct"] += 1

    topic_lines = "\n".join(
        f"  - {t}: {s['correct']}/{s['total']} correct "
        f"({int(s['correct']/s['total']*100)}% accuracy)"
        for t, s in sorted(topic_stats.items(), key=lambda x: x[1]["correct"]/x[1]["total"])
    )
    weak_topics = [t for t, s in topic_stats.items() if s["correct"] / s["total"] < 0.6]
    ability_label = (
        "Advanced" if theta > 1.5 else
        "Proficient" if theta > 0.5 else
        "Developing" if theta > -0.5 else "Foundational"
    )

    return f"""You are an expert GRE tutor. A student just finished an adaptive diagnostic test.

Student: {student_id}
Ability estimate: {theta:.2f} (logit scale) — {ability_label}
Overall accuracy: {sum(r["is_correct"] for r in responses)}/{len(responses)} correct

Topic breakdown:
{topic_lines}

Weak topics (< 60% accuracy): {", ".join(weak_topics) or "None — great performance!"}

Generate a concise **3-Step Personalised Study Plan** using this format exactly:

**Step 1 — [Focus Area]**
[2-3 sentences of specific, actionable advice]

**Step 2 — [Focus Area]**
[2-3 sentences of specific, actionable advice]

**Step 3 — [Focus Area]**
[2-3 sentences of specific, actionable advice]

**Quick Win**
[One sentence: the single most impactful thing to do this week]

Be encouraging, specific, and reference the student's actual topic data."""


async def generate_study_plan(student_id: str, theta: float, responses: list[dict]) -> str:
    if not ANTHROPIC_API_KEY:
        return "⚠️ Set ANTHROPIC_API_KEY in your .env file to enable AI study plans."
    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            messages=[{"role": "user", "content": _build_prompt(student_id, theta, responses)}],
        )
        return msg.content[0].text
    except anthropic.BadRequestError as e:
        return f"⚠️ Anthropic API error: {e}. Please check your credits at console.anthropic.com/settings/billing."
    except anthropic.AuthenticationError:
        return "⚠️ Invalid ANTHROPIC_API_KEY. Please check your .env file."
    except Exception as e:
        return f"⚠️ Could not generate study plan: {e}"


# ══════════════════════════════════════════════════════════════════════════════
# PYDANTIC SCHEMAS
# ══════════════════════════════════════════════════════════════════════════════

class StartRequest(BaseModel):
    student_id: str = Field(..., min_length=1)

class SubmitRequest(BaseModel):
    session_id: str
    question_id: str
    user_answer: str

class StartResponse(BaseModel):
    session_id: str
    student_id: str
    message: str

class QuestionOut(BaseModel):
    id: str
    text: str
    options: list[str]
    difficulty: float
    topic: str
    tags: list[str]

class NextQuestionResponse(BaseModel):
    session_id: str
    question_number: int
    total_questions: int
    current_ability: float
    question: QuestionOut

class SubmitResponse(BaseModel):
    is_correct: bool
    correct_answer: str
    explanation: str
    updated_ability: float
    session_complete: bool
    questions_answered: int
    total_questions: int

class ResponseRecord(BaseModel):
    question_id: str
    topic: str
    difficulty: float
    user_answer: str
    is_correct: bool
    ability_after: float

class SessionSummary(BaseModel):
    session_id: str
    student_id: str
    final_ability: float
    questions_answered: int
    responses: list[ResponseRecord]
    study_plan: str | None
    is_complete: bool


# ══════════════════════════════════════════════════════════════════════════════
# APP + ROUTES
# ══════════════════════════════════════════════════════════════════════════════

@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_db()
    await seed_questions()
    yield
    await close_db()


app = FastAPI(
    title="Adaptive Diagnostic Engine",
    description="IRT-powered adaptive testing + Anthropic AI study plans",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def _oid(id_str: str, label: str = "id") -> ObjectId:
    try:
        return ObjectId(id_str)
    except Exception:
        raise HTTPException(status_code=400, detail=f"Invalid {label} format.")


# ── Health ──────────────────────────────────────────────────────────────────────

@app.get("/health", tags=["Health"])
async def health():
    db = get_db()
    count = await db["questions"].count_documents({})
    return {"status": "healthy", "questions_in_db": count}


# ── POST /sessions/start ────────────────────────────────────────────────────────

@app.post("/sessions/start", response_model=StartResponse, status_code=201, tags=["Sessions"])
async def start_session(body: StartRequest) -> StartResponse:
    """Create a new adaptive test session at baseline ability θ = 0."""
    db = get_db()
    doc = {
        "student_id": body.student_id,
        "ability": BASELINE_ABILITY,
        "questions_answered": 0,
        "responses": [],
        "question_ids_seen": [],
        "is_complete": False,
        "study_plan": None,
        "created_at": datetime.now(timezone.utc),
    }
    result = await db["sessions"].insert_one(doc)
    return StartResponse(
        session_id=str(result.inserted_id),
        student_id=body.student_id,
        message=f"Session started. Answer up to {MAX_QUESTIONS} questions. Good luck!",
    )


# ── GET /questions/next/{session_id} ────────────────────────────────────────────

@app.get("/questions/next/{session_id}", response_model=NextQuestionResponse, tags=["Questions"])
async def next_question(session_id: str) -> NextQuestionResponse:
    """
    Select the next question via Maximum Fisher Information (MFI):
    picks the unseen item whose difficulty logit is closest to θ,
    maximising information gain per the IRT model.
    """
    db = get_db()
    session = await db["sessions"].find_one({"_id": _oid(session_id, "session_id")})
    if not session:
        raise HTTPException(404, "Session not found.")
    if session["is_complete"]:
        raise HTTPException(400, "Session complete. Retrieve summary at GET /sessions/{id}.")
    if session["questions_answered"] >= MAX_QUESTIONS:
        raise HTTPException(400, "Maximum questions reached.")

    all_q = await db["questions"].find({}).to_list(500)
    selected = select_next_question(session["ability"], all_q, session["question_ids_seen"])
    if not selected:
        raise HTTPException(404, "No unseen questions remaining.")

    return NextQuestionResponse(
        session_id=session_id,
        question_number=session["questions_answered"] + 1,
        total_questions=MAX_QUESTIONS,
        current_ability=round(session["ability"], 4),
        question=QuestionOut(
            id=str(selected["_id"]),
            text=selected["text"],
            options=selected["options"],
            difficulty=selected["difficulty"],
            topic=selected["topic"],
            tags=selected.get("tags", []),
        ),
    )


# ── POST /sessions/submit ───────────────────────────────────────────────────────

@app.post("/sessions/submit", response_model=SubmitResponse, tags=["Sessions"])
async def submit_answer(body: SubmitRequest) -> SubmitResponse:
    """
    Record answer → update ability via IRT → select next question.
    Triggers AI study plan generation when MAX_QUESTIONS is reached.
    """
    db = get_db()
    session = await db["sessions"].find_one({"_id": _oid(body.session_id, "session_id")})
    if not session:
        raise HTTPException(404, "Session not found.")
    if session["is_complete"]:
        raise HTTPException(400, "Session already complete.")

    question = await db["questions"].find_one({"_id": _oid(body.question_id, "question_id")})
    if not question:
        raise HTTPException(404, "Question not found.")

    # Evaluate answer
    is_correct = body.user_answer.strip().lower() == question["correct_answer"].strip().lower()

    # IRT ability update
    b = difficulty_to_logit(question["difficulty"])
    new_theta = update_ability(session["ability"], b, is_correct)

    # Build response record
    record = {
        "question_id": body.question_id,
        "topic": question["topic"],
        "difficulty": question["difficulty"],
        "user_answer": body.user_answer,
        "is_correct": is_correct,
        "ability_after": new_theta,
    }

    questions_answered = session["questions_answered"] + 1
    is_complete = questions_answered >= MAX_QUESTIONS

    # Generate AI study plan on session end
    study_plan = None
    if is_complete:
        all_responses = session["responses"] + [record]
        study_plan = await generate_study_plan(session["student_id"], new_theta, all_responses)

    # Persist
    await db["sessions"].update_one(
        {"_id": _oid(body.session_id)},
        {
            "$set": {
                "ability": new_theta,
                "questions_answered": questions_answered,
                "question_ids_seen": session["question_ids_seen"] + [body.question_id],
                "is_complete": is_complete,
                **({"study_plan": study_plan} if is_complete else {}),
            },
            "$push": {"responses": record},
        },
    )

    return SubmitResponse(
        is_correct=is_correct,
        correct_answer=question["correct_answer"],
        explanation=question.get("explanation", ""),
        updated_ability=round(new_theta, 4),
        session_complete=is_complete,
        questions_answered=questions_answered,
        total_questions=MAX_QUESTIONS,
    )


# ── GET /sessions/{session_id} ──────────────────────────────────────────────────

@app.get("/sessions/{session_id}", response_model=SessionSummary, tags=["Sessions"])
async def get_session(session_id: str) -> SessionSummary:
    """Return the full session summary including the AI-generated study plan."""
    db = get_db()
    session = await db["sessions"].find_one({"_id": _oid(session_id, "session_id")})
    if not session:
        raise HTTPException(404, "Session not found.")
    return SessionSummary(
        session_id=session_id,
        student_id=session["student_id"],
        final_ability=round(session["ability"], 4),
        questions_answered=session["questions_answered"],
        responses=[ResponseRecord(**r) for r in session.get("responses", [])],
        study_plan=session.get("study_plan"),
        is_complete=session["is_complete"],
    )