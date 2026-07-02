# AI Job Copilot – ATS Resume Intelligence Platform

An AI-powered platform that analyzes how well a resume matches a job description, using retrieval-augmented generation (RAG), hybrid keyword + semantic matching, explainable scoring, and skill-gap quizzes.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    Next.js 16 Frontend (App Router)              │
│  Home │ My Resume │ Analyze │ My Skill Validation │ Dashboard    │
│                    │ Feedback                                    │
│              Auth: Clerk                                         │
└──────────────────────────────┬──────────────────────────────────┘
                               │ /backend/* rewrite proxy
┌──────────────────────────────▼──────────────────────────────────┐
│                      FastAPI REST API                            │
│  /resume/*  /job/upload  /analysis/*  /quiz/*                   │
│  /users/me/*  /feedback                                          │
└──────────────────────────────┬──────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────┐
│                     Core Logic Layer                             │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────┐   │
│  │   NLP    │  │   RAG    │  │ Matching │  │Explainability│   │
│  │ Pipeline │  │ Pipeline │  │  Engine  │  │    Layer     │   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────────┘   │
└──────────────────────────────┬──────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────┐
│                       Data Layer                                 │
│  ┌────────────────┐  ┌────────────┐  ┌───────────────────┐     │
│  │  PostgreSQL    │  │  pgvector  │  │  In-Memory Cache  │     │
│  │  (Neon)        │  │ (Vectors)  │  │  (LRU + Metrics)  │     │
│  └────────────────┘  └────────────┘  └───────────────────┘     │
└─────────────────────────────────────────────────────────────────┘
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 16 (App Router), React 19, TypeScript, Tailwind CSS |
| Auth | Clerk |
| Backend | Python, FastAPI |
| Database | PostgreSQL (Neon) + pgvector |
| AI | OpenAI API (GPT-4o-mini, text-embedding-3-small) |
| Email | Resend (feedback notifications) |
| Frontend hosting | Vercel |
| Backend hosting | Render |
| CI | GitHub Actions |
| Testing | pytest |

Note: `src/ui/app.py` (Streamlit) exists in the repo from an earlier prototype but is not part of the active application — the Next.js frontend is the real UI.

## Key Features

### 1. RAG Pipeline
- Section-aware chunking (512 tokens, 50 token overlap)
- OpenAI text-embedding-3-small (1536 dimensions)
- pgvector for vector similarity search
- Cosine similarity retrieval with configurable threshold

### 2. Hybrid Matching Engine
- Exact, normalized, and phrase-based keyword matching
- Embedding-based semantic similarity scoring
- Category weighting (core skills weighted higher than supporting)
- False-equivalence guardrails (e.g. "Java" is never matched against "JavaScript")
- `score = 0.4 × keyword + 0.4 × semantic + 0.2 × category`

### 3. Explainability Layer
Every analysis includes a plain-language summary, matched skills with resume evidence snippets, missing skills with actionable tips, and honest bullet-point rewrites that never fabricate skills or metrics not already present in the original resume.

### 4. Resume Management
- Upload via PDF or pasted text
- Multiple saved resumes per user with one marked "active"
- Rename and switch between resumes
- Skill extraction runs automatically in the background on upload

### 5. Skill Validation Quizzes
- AI-generated multiple-choice quizzes per missing skill, three difficulty levels (easy/medium/hard)
- Skills auto-resolve (no longer tracked as a gap) once they appear in a newer resume
- Progress persists per skill; any level can be retaken at any time

### 6. Feedback
- In-app feedback/suggestion form, stored in the database and emailed to the site owner via Resend

### 7. Caching Layer
- LRU cache with TTL for JD parsing, resume parsing, and skill/JD normalization results

## Project Structure

```
ai_job_copilot/
├── .github/workflows/ci_cd.yml    # CI pipeline
├── docs/
│   ├── architecture.md
│   └── database_schema.md
├── frontend/                      # Next.js app (the real UI)
│   ├── app/(app)/                 # Home, Resume, Analyze, Skills, Dashboard, Feedback
│   ├── components/
│   └── lib/api.ts                 # Backend API client
├── src/
│   ├── api/
│   │   ├── main.py                # FastAPI entry point
│   │   ├── auth.py                # Clerk JWT verification
│   │   ├── routes/                # analysis, quiz, users/feedback
│   │   └── schemas/
│   ├── core/                      # config, logging, exceptions, email
│   ├── database/                  # SQLAlchemy models, session
│   ├── nlp/                       # parsing, skill extraction, normalization
│   ├── rag/                       # chunking, embeddings, retrieval
│   ├── matching/                  # scoring engine, explainability
│   ├── evaluation/                # evaluation framework, feedback
│   ├── cache/
│   └── ui/                        # legacy Streamlit prototype (unused)
├── tests/
├── render.yaml                    # Render deploy blueprint (backend)
├── requirements.txt
├── .env.example
└── README.md
```

## Setup & Installation

### Prerequisites
- Python 3.11+
- Node.js 20+
- PostgreSQL with the pgvector extension (Neon works well)
- OpenAI API key
- Clerk account (auth)
- Resend account (optional, for feedback email notifications)

### 1. Clone and install backend dependencies

```bash
git clone https://github.com/veenadhariponukumati/AI_JOB_COPILOT.git
cd AI_JOB_COPILOT
pip install -r requirements.txt
```

### 2. Configure backend environment

```bash
cp .env.example .env
# Fill in DATABASE_URL, OPENAI_API_KEY, CLERK_SECRET_KEY, CLERK_FRONTEND_API,
# and (optionally) RESEND_API_KEY / FEEDBACK_NOTIFY_EMAIL
```

### 3. Initialize the database

```bash
python -m src.database.init_db
```

### 4. Run the backend

```bash
PYTHONPATH=. uvicorn src.api.main:app --host 127.0.0.1 --port 8000 --reload
```

### 5. Install and run the frontend

```bash
cd frontend
npm install
cp .env.local.example .env.local   # fill in your Clerk publishable/secret keys
npm run dev
```

The frontend proxies `/backend/*` requests to the FastAPI server (configurable via the `BACKEND_URL` env var for production).

### 6. Run tests

```bash
pytest tests/unit/ -v
pytest tests/integration/ -v
pytest --cov=src --cov-report=html
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/resume/upload` | Upload and parse a pasted-text resume |
| POST | `/resume/upload-file` | Upload and parse a PDF resume |
| POST | `/job/upload` | Upload and parse a job description |
| POST | `/analysis/run` | Start an ATS analysis (background job) |
| GET | `/analysis/{analysis_id}` | Poll for analysis results |
| POST | `/quiz/start` | Generate a skill validation quiz |
| POST | `/quiz/submit` | Submit quiz answers for grading |
| POST | `/feedback` | Submit user feedback/suggestions |
| GET | `/users/me` | Current user profile |
| GET | `/users/me/resumes` | List saved resumes |
| DELETE | `/users/me/resumes/{resume_id}` | Delete a resume |
| POST | `/users/me/resumes/{resume_id}/activate` | Set a resume as active |
| PATCH | `/users/me/resumes/{resume_id}` | Rename a resume |
| GET | `/users/me/resume-skills` | Skills extracted from the active resume |
| GET | `/users/me/skills` | Skill validation progress (quiz history) |
| DELETE | `/users/me/skills` | Clear all tracked skill progress |
| DELETE | `/users/me/skills/{skill_name}` | Remove one tracked skill |
| GET | `/users/me/history` | Past analysis history |
| GET | `/users/me/feedback` | Current user's submitted feedback |
| GET | `/health` | Health check |
| GET | `/metrics/cache` | Cache performance metrics |

## Database Schema

PostgreSQL schema, key tables:
- `users` — user accounts (linked to Clerk identity)
- `resumes` — uploaded resumes, parsed sections, extracted skills, active flag
- `job_descriptions` — parsed job requirements
- `ats_analyses` — analysis results, scores, evidence, optimized bullets
- `document_chunks` — RAG chunks with pgvector embeddings
- `quiz_results` — generated quizzes and grading
- `skill_progress` — per-user, per-skill quiz progress and resolution state
- `user_feedback` — feedback/suggestion submissions
- `cache_entries` — cache hit/miss metrics

## Scoring Methodology

```
Overall Score = (0.4 × Keyword Score) + (0.4 × Semantic Score) + (0.2 × Category Score)
```

Category weights: Core 2.0x, Technical 1.5x, Functional 1.2x, Behavioral 0.8x, Supporting 0.6x.

## Known Limitations

- LLM-generated quiz answer keys are not always correct; the prompt asks the model to self-verify but this is a mitigation, not a guarantee.
- A handful of unit/integration tests currently fail after recent matching-engine and parser changes and need updating to match the new expected behavior.
- No rate limiting on OpenAI-backed endpoints yet — public deployment should add this before high-traffic use.

## License

MIT
