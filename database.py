"""
database.py — MongoDB connection + Question seed data
=====================================================
Handles:
  - Async Motor client (connect / close / get_db)
  - 25 GRE-style questions across 5 topics
  - Auto-seed on first run (idempotent)

Run standalone to seed:  python database.py
"""

import asyncio
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import IndexModel, ASCENDING
import os
from dotenv import load_dotenv

load_dotenv()

MONGODB_URI   = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
DATABASE_NAME = os.getenv("DATABASE_NAME", "adaptive_engine")

_client: AsyncIOMotorClient | None = None


# ── Connection ──────────────────────────────────────────────────────────────────

async def connect_db() -> None:
    global _client
    _client = AsyncIOMotorClient(MONGODB_URI)
    await _client.admin.command("ping")
    print("✓ Connected to MongoDB")


async def close_db() -> None:
    global _client
    if _client:
        _client.close()
        _client = None


def get_db() -> AsyncIOMotorDatabase:
    if _client is None:
        raise RuntimeError("DB not connected. Call connect_db() first.")
    return _client[DATABASE_NAME]


# ── Seed Data ───────────────────────────────────────────────────────────────────

QUESTIONS = [
    # ── Algebra (5 questions, difficulty 0.1 → 0.9) ───────────────────────────
    {
        "text": "If 3x + 7 = 22, what is the value of x?",
        "options": ["A) 3", "B) 5", "C) 7", "D) 9"],
        "correct_answer": "B) 5",
        "difficulty": 0.1,
        "topic": "Algebra",
        "tags": ["linear equations", "arithmetic"],
        "explanation": "3x = 22 − 7 = 15, so x = 5.",
    },
    {
        "text": "Which expression is equivalent to (x + 3)²?",
        "options": ["A) x² + 9", "B) x² + 6x + 9", "C) x² + 3x + 9", "D) x² + 6x + 6"],
        "correct_answer": "B) x² + 6x + 9",
        "difficulty": 0.2,
        "topic": "Algebra",
        "tags": ["polynomials", "expansion"],
        "explanation": "(x+3)² = x² + 2·3·x + 9 = x² + 6x + 9.",
    },
    {
        "text": "If f(x) = 2x² − 3x + 1, what is f(−1)?",
        "options": ["A) −4", "B) 2", "C) 6", "D) −2"],
        "correct_answer": "C) 6",
        "difficulty": 0.35,
        "topic": "Algebra",
        "tags": ["functions", "substitution"],
        "explanation": "f(−1) = 2(1) − 3(−1) + 1 = 2 + 3 + 1 = 6.",
    },
    {
        "text": "Solve for x: |2x − 5| = 9",
        "options": ["A) x = 7 only", "B) x = −2 only", "C) x = 7 or x = −2", "D) x = 2 or x = −7"],
        "correct_answer": "C) x = 7 or x = −2",
        "difficulty": 0.55,
        "topic": "Algebra",
        "tags": ["absolute value", "equations"],
        "explanation": "2x−5 = 9 → x = 7;  or  2x−5 = −9 → x = −2.",
    },
    {
        "text": "If roots of x² − px + q = 0 are r and s, which equals r² + s²?",
        "options": ["A) p² + 2q", "B) p² − 2q", "C) q² − 2p", "D) (p−q)²"],
        "correct_answer": "B) p² − 2q",
        "difficulty": 0.8,
        "topic": "Algebra",
        "tags": ["Vieta's formulas", "quadratics"],
        "explanation": "r+s = p and rs = q, so r²+s² = (r+s)² − 2rs = p² − 2q.",
    },

    # ── Geometry (5 questions) ────────────────────────────────────────────────
    {
        "text": "A rectangle has length 8 and width 5. What is its area?",
        "options": ["A) 13", "B) 26", "C) 40", "D) 45"],
        "correct_answer": "C) 40",
        "difficulty": 0.1,
        "topic": "Geometry",
        "tags": ["area", "rectangles"],
        "explanation": "Area = length × width = 8 × 5 = 40.",
    },
    {
        "text": "In triangle ABC, angle A = 50° and angle B = 70°. What is angle C?",
        "options": ["A) 50°", "B) 60°", "C) 70°", "D) 80°"],
        "correct_answer": "B) 60°",
        "difficulty": 0.15,
        "topic": "Geometry",
        "tags": ["triangles", "angle sum"],
        "explanation": "Angles sum to 180°: C = 180 − 50 − 70 = 60°.",
    },
    {
        "text": "A circle has radius 7. What is its area? (Use π ≈ 3.14)",
        "options": ["A) 43.96", "B) 49", "C) 153.86", "D) 21.98"],
        "correct_answer": "C) 153.86",
        "difficulty": 0.25,
        "topic": "Geometry",
        "tags": ["circles", "area"],
        "explanation": "Area = πr² = 3.14 × 49 ≈ 153.86.",
    },
    {
        "text": "Two parallel lines cut by a transversal. One interior angle is 65°. What is the co-interior angle?",
        "options": ["A) 65°", "B) 90°", "C) 115°", "D) 125°"],
        "correct_answer": "C) 115°",
        "difficulty": 0.4,
        "topic": "Geometry",
        "tags": ["parallel lines", "angles"],
        "explanation": "Co-interior angles are supplementary: 180° − 65° = 115°.",
    },
    {
        "text": "A cone has radius 3 and height 4. What is its volume? (V = ⅓πr²h, π ≈ 3.14)",
        "options": ["A) 12.56", "B) 37.68", "C) 50.24", "D) 75.36"],
        "correct_answer": "B) 37.68",
        "difficulty": 0.65,
        "topic": "Geometry",
        "tags": ["3D geometry", "volume"],
        "explanation": "V = (1/3) × 3.14 × 9 × 4 = 37.68.",
    },

    # ── Arithmetic (5 questions) ──────────────────────────────────────────────
    {
        "text": "What is 15% of 240?",
        "options": ["A) 30", "B) 36", "C) 42", "D) 48"],
        "correct_answer": "B) 36",
        "difficulty": 0.15,
        "topic": "Arithmetic",
        "tags": ["percentages"],
        "explanation": "10% = 24, 5% = 12, total = 36.",
    },
    {
        "text": "What is the LCM of 12 and 18?",
        "options": ["A) 6", "B) 24", "C) 36", "D) 72"],
        "correct_answer": "C) 36",
        "difficulty": 0.25,
        "topic": "Arithmetic",
        "tags": ["LCM", "number theory"],
        "explanation": "12 = 2²×3; 18 = 2×3²; LCM = 2²×3² = 36.",
    },
    {
        "text": "A train travels 180 km in 2.5 hours. What is its average speed?",
        "options": ["A) 60 km/h", "B) 70 km/h", "C) 72 km/h", "D) 80 km/h"],
        "correct_answer": "C) 72 km/h",
        "difficulty": 0.3,
        "topic": "Arithmetic",
        "tags": ["speed-distance-time"],
        "explanation": "Speed = 180 ÷ 2.5 = 72 km/h.",
    },
    {
        "text": "How many prime numbers exist between 20 and 40?",
        "options": ["A) 3", "B) 4", "C) 5", "D) 6"],
        "correct_answer": "B) 4",
        "difficulty": 0.45,
        "topic": "Arithmetic",
        "tags": ["primes", "number theory"],
        "explanation": "23, 29, 31, 37 — four primes.",
    },
    {
        "text": "If the price of an item rises by 20% then drops by 20%, what is the net % change?",
        "options": ["A) 0%", "B) −2%", "C) −4%", "D) +4%"],
        "correct_answer": "C) −4%",
        "difficulty": 0.6,
        "topic": "Arithmetic",
        "tags": ["percentages", "successive changes"],
        "explanation": "1.2 × 0.8 = 0.96 → net change = −4%.",
    },

    # ── Data Analysis / Statistics (5 questions) ──────────────────────────────
    {
        "text": "The mean of five numbers is 12. Four of them are 10, 11, 13, 14. What is the fifth?",
        "options": ["A) 10", "B) 11", "C) 12", "D) 13"],
        "correct_answer": "C) 12",
        "difficulty": 0.2,
        "topic": "Data Analysis",
        "tags": ["mean", "arithmetic"],
        "explanation": "Total = 60; sum of four = 48; fifth = 60 − 48 = 12.",
    },
    {
        "text": "A bag has 4 red, 3 blue, 5 green balls. What is P(not red)?",
        "options": ["A) 1/3", "B) 1/4", "C) 3/4", "D) 2/3"],
        "correct_answer": "D) 2/3",
        "difficulty": 0.3,
        "topic": "Data Analysis",
        "tags": ["probability"],
        "explanation": "P(not red) = 8/12 = 2/3.",
    },
    {
        "text": "P(A) = 0.4, P(B) = 0.5, A and B are independent. What is P(A∩B)?",
        "options": ["A) 0.1", "B) 0.2", "C) 0.4", "D) 0.9"],
        "correct_answer": "B) 0.2",
        "difficulty": 0.5,
        "topic": "Data Analysis",
        "tags": ["probability", "independence"],
        "explanation": "P(A∩B) = P(A)·P(B) = 0.4 × 0.5 = 0.2.",
    },
    {
        "text": "A data set has median 50 and mean 55. What can be inferred?",
        "options": [
            "A) Left-skewed distribution",
            "B) Right-skewed distribution",
            "C) Symmetric distribution",
            "D) No outliers present",
        ],
        "correct_answer": "B) Right-skewed distribution",
        "difficulty": 0.65,
        "topic": "Data Analysis",
        "tags": ["skewness", "descriptive statistics"],
        "explanation": "Mean > median implies a positive (right) skew.",
    },
    {
        "text": "The standard deviation of {2, 4, 4, 4, 5, 5, 7, 9} is 2. What is the variance?",
        "options": ["A) 1", "B) 2", "C) 4", "D) 8"],
        "correct_answer": "C) 4",
        "difficulty": 0.45,
        "topic": "Data Analysis",
        "tags": ["variance", "standard deviation"],
        "explanation": "Variance = SD² = 2² = 4.",
    },

    # ── Vocabulary / Verbal (5 questions) ─────────────────────────────────────
    {
        "text": "Choose the word most similar in meaning to EPHEMERAL.",
        "options": ["A) Eternal", "B) Transient", "C) Substantial", "D) Recurrent"],
        "correct_answer": "B) Transient",
        "difficulty": 0.4,
        "topic": "Vocabulary",
        "tags": ["synonyms", "GRE word list"],
        "explanation": "Ephemeral = lasting a very short time → synonym: transient.",
    },
    {
        "text": "Choose the word most nearly OPPOSITE in meaning to LACONIC.",
        "options": ["A) Brief", "B) Taciturn", "C) Verbose", "D) Succinct"],
        "correct_answer": "C) Verbose",
        "difficulty": 0.5,
        "topic": "Vocabulary",
        "tags": ["antonyms"],
        "explanation": "Laconic = using few words. Antonym: verbose (using too many words).",
    },
    {
        "text": "The scholar's _______ remarks, though brief, contained the essence of decades of research.",
        "options": ["A) Verbose", "B) Pedantic", "C) Diffuse", "D) Pithy"],
        "correct_answer": "D) Pithy",
        "difficulty": 0.6,
        "topic": "Vocabulary",
        "tags": ["sentence completion"],
        "explanation": "Pithy = concise and meaningfully expressed — fits 'brief but containing essence'.",
    },
    {
        "text": "ENERVATE : VIGOR :: PERPLEX : ___",
        "options": ["A) Confusion", "B) Energy", "C) Clarity", "D) Wisdom"],
        "correct_answer": "C) Clarity",
        "difficulty": 0.8,
        "topic": "Vocabulary",
        "tags": ["analogies", "GRE verbal"],
        "explanation": "Enervate removes vigor; perplex removes clarity. Pattern: X removes Y.",
    },
    {
        "text": "If log₂(x) + log₂(x−2) = 3, what is x?",
        "options": ["A) 2", "B) 3", "C) 4", "D) −2"],
        "correct_answer": "C) 4",
        "difficulty": 0.9,
        "topic": "Algebra",
        "tags": ["logarithms", "hard"],
        "explanation": "log₂[x(x−2)] = 3 → x(x−2)=8 → x²−2x−8=0 → x=4 (positive root only).",
    },
]


# ── Seed function ───────────────────────────────────────────────────────────────

async def seed_questions() -> None:
    db = get_db()
    collection = db["questions"]

    existing = await collection.count_documents({})
    if existing >= len(QUESTIONS):
        print(f"✓ Questions already seeded ({existing} docs). Skipping.")
        return

    await collection.drop()
    await collection.insert_many(QUESTIONS)
    await collection.create_index([("difficulty", ASCENDING)])
    await collection.create_index([("topic", ASCENDING)])
    print(f"✓ Seeded {len(QUESTIONS)} questions with indexes on difficulty + topic.")


# ── Run standalone ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    async def main():
        await connect_db()
        await seed_questions()
        await close_db()
    asyncio.run(main())
