# AI Job Copilot

A resume-to-job-description matching platform. It parses a resume and a job description, extracts skills using an LLM, retrieves supporting evidence from the resume with a RAG pipeline, and produces a weighted match score with an explainable breakdown, missing-skill list, and optional skill-validation quizzes.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                Next.js 16 Frontend (App Router)                  │
│  Home │ My Resume │ Analyze │ My Skill Validation │ Dashboard    │
│                    │ Feedback                                    │
│              Auth: Clerk (clerkMiddleware)                       │
└──────────────────────────────┬──────────────────────────────────┘
                               │ /backend/* rewrite proxy (next.config.ts)
┌──────────────────────────────▼──────────────────────────────────┐
│                      FastAPI REST API                            │
│  /resume/*  /job/upload  /analysis/*  /quiz/*                    │
│  /users/me/*  /feedback  /health  /metrics/cache                 │
└──────────────────────────────┬──────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────┐
│                     Core Logic Layer                             │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────┐    │
│  │   NLP    │  │   RAG    │  │ Matching │  │Explainability│    │
│  │ Pipeline │  │ Pipeline │  │  Engine  │  │    Layer     │    │
│  └──────────┘  └──────────┘  └──────────┘  └──────────────┘    │
└──────────────────────────────┬──────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────┐
│                       Data Layer                                 │
│  ┌────────────────┐  ┌────────────┐  ┌───────────────────┐      │
│  │  PostgreSQL    │  │  pgvector  │  │  In-Memory Cache  │      │
│  │  (Neon)        │  │ (Vectors)  │  │  (LRU + Metrics)  │      │
│  └────────────────┘  └────────────┘  └───────────────────┘      │
└─────────────────────────────────────────────────────────────────┘
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 16 (App Router), React 19, TypeScript, Tailwind CSS |
| Auth | Clerk |
| Backend | Python, FastAPI |
| Database | PostgreSQL (Neon) + pgvector |
| AI | OpenAI API (`gpt-4o-mini`, `text-embedding-3-small`) |
| Email | Resend (feedback notifications) |
| Frontend hosting | Vercel |
| Backend hosting | Render |
| CI | GitHub Actions |
| Testing | pytest |

`src/ui/app.py` is a Streamlit prototype from an earlier iteration of the project. It calls the same FastAPI backend and still runs, but it is not part of the deployed application, is not covered by CI, and has no container/deploy config — the Next.js frontend is the active UI.

## Key Features

### RAG Pipeline
- Section-aware document chunking: whole sections are kept intact when they fit in one chunk; larger sections are split with sentence-boundary-aware overlap (`src/rag/chunker.py`)
- Chunk size / overlap are configurable via `CHUNK_SIZE` / `CHUNK_OVERLAP` settings (documented default: 512 tokens / 50 token overlap, approximated at 4 characters per token)
- Embeddings via OpenAI `text-embedding-3-small` (1536 dimensions), batched in groups of 20
- Retrieval via pgvector cosine distance (`<=>` operator), filtered by a configurable similarity threshold and `top_k`

### Hybrid Matching Engine
Skills are matched in layered order, each layer only attempting skills the previous one didn't resolve:
1. Alternative-group matching (JD skill satisfied by any one of several acceptable options)
2. Exact string match
3. Deterministic normalization (case/punctuation/version-suffix stripping)
4. A small hardcoded alias table (`js`/`ts`/`py` and similar)
5. Substring phrase matching, blocked by an explicit false-equivalence list (e.g. "Java" never matches "JavaScript"; "React" never matches "React Native")
6. LLM-derived semantic canonicalization, accepted only above a 0.80 confidence threshold and only if the LLM's cited evidence can be traced back to actual resume text
7. RAG-retrieved evidence above the similarity threshold

Overall score:
```
unified_coverage = (exact_and_normalized_matches + 0.85 × semantic_and_rag_matches) / total_jd_skills
overall_score    = 0.70 × unified_coverage + 0.30 × category_score
```
Category weights: Core 2.0x, Technical 1.5x, Functional 1.2x, Behavioral 0.8x, Supporting 0.6x.

The engine also accepts `keyword_weight` / `semantic_weight` / `category_weight` constructor parameters (and exposes them in the response as `weights_used`), but the score formula above does not currently consume them — they have no effect on the computed `overall_score`.

### Explainability Layer
Each analysis includes an LLM-generated plain-language summary, matched skills with resume evidence snippets, missing skills, and rewritten resume bullets. The bullet-rewrite prompt is constrained to not introduce skills or metrics absent from the original resume, and a regex-based verification step checks that cited evidence snippets actually appear in the source text. If the OpenAI call fails, both the explanation and bullet rewrites fall back to a deterministic, non-LLM summary rather than failing the request.

### Resume Management
- Upload via pasted text or PDF (parsed with PyPDF2)
- Multiple saved resumes per user, one marked active
- Rename, switch, and delete
- Skill extraction runs as a background task on upload

### Skill Validation Quizzes
- LLM-generated multiple-choice quizzes per missing skill, three difficulty levels
- Skill progress persists per user/skill; quizzes can be retaken
- A resume-skills endpoint has retry-with-backoff logic (3 attempts) if background extraction hasn't completed yet

### Feedback
In-app form, stored in the database, and emailed to a configured address via Resend.

### Caching
In-process LRU cache with TTL, used for JD parsing, resume parsing, and skill/JD semantic normalization. This cache is a single-process, in-memory dictionary — it does not share state across multiple backend instances/workers and resets on every restart or deploy. A `cache_entries` database table exists in the schema but is not written to by the current cache implementation.

## Project Structure

```
ai_job_copilot/
├── .github/workflows/ci_cd.yml    # CI: lint, test, build validation
├── docs/
│   ├── architecture.md
│   └── database_schema.md
├── frontend/                      # Next.js app (the active UI)
│   ├── app/(app)/                 # Home, Resume, Analyze, Skills, Dashboard, Feedback
│   ├── app/sign-in/, app/sign-up/ # Clerk auth pages
│   ├── components/
│   ├── lib/api.ts                 # Backend API client
│   ├── proxy.ts                   # Clerk middleware (route protection)
│   └── next.config.ts             # /backend/* rewrite to BACKEND_URL
├── src/
│   ├── api/
│   │   ├── main.py                # FastAPI entry point, CORS, rate limiting, error handlers
│   │   ├── auth.py                # Clerk JWT verification (JWKS, RS256)
│   │   ├── routes/                # analysis, quiz, users, feedback
│   │   └── schemas/
│   ├── core/                      # config, logging, exceptions, rate limiting
│   ├── database/                  # SQLAlchemy models, session, init
│   ├── nlp/                       # parsing, LLM skill extraction, normalization
│   ├── rag/                       # chunking, embeddings, pgvector retrieval
│   ├── matching/                  # scoring engine, explainability
│   ├── evaluation/                # fixed-sample eval harness, feedback CRUD
│   ├── cache/
│   └── ui/                        # Streamlit prototype (not part of the deployed app)
├── tests/
│   ├── unit/
│   └── integration/
├── render.yaml                    # Render deploy blueprint (backend)
├── runtime.txt                    # Pins Python 3.11.9 for Render
├── requirements.txt
├── .env.example
└── README.md
```

## Setup & Installation

### Prerequisites
- Python 3.11 (pinned; newer versions break the `pandas==2.1.3` build — see note below)
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

The frontend proxies `/backend/*` requests to the FastAPI server (`BACKEND_URL` env var controls the target; defaults to `http://127.0.0.1:8000` locally).

Note: `runtime.txt` pins the backend to Python 3.11.9 for Render deploys. Newer Python versions (3.13+) break the `pandas==2.1.3` build's Cython extensions, so keep this pin if you fork/redeploy.

### 6. Run tests

```bash
pytest tests/unit/ -v
pytest tests/integration/ -v
pytest --cov=src --cov-report=html
```

## API Endpoints

| Method | Endpoint | Auth | Rate limit | Description |
|--------|----------|------|------------|-------------|
| POST | `/resume/upload` | optional | 10/min | Upload and parse a pasted-text resume |
| POST | `/resume/upload-file` | optional | 10/min | Upload and parse a PDF resume |
| POST | `/job/upload` | none | 15/min | Upload and parse a job description |
| POST | `/analysis/run` | optional | 10/min | Start an ATS analysis (background job) |
| GET | `/analysis/{analysis_id}` | none | none | Poll for analysis results |
| GET | `/history` | none | none | List analyses (not scoped to a user — see Known Limitations) |
| POST | `/quiz/start` | none | 15/min | Generate a skill validation quiz |
| POST | `/quiz/submit` | none | none | Submit quiz answers for grading |
| POST | `/feedback` | optional | 5/min | Submit user feedback/suggestions |
| GET | `/users/me` | required | none | Current user profile |
| GET | `/users/me/resumes` | required | none | List saved resumes |
| DELETE | `/users/me/resumes/{resume_id}` | required | none | Delete a resume |
| POST | `/users/me/resumes/{resume_id}/activate` | required | none | Set a resume as active |
| PATCH | `/users/me/resumes/{resume_id}` | required | none | Rename a resume |
| GET | `/users/me/resume-skills` | required | none | Skills extracted from the active resume |
| GET | `/users/me/skills` | required | none | Skill validation progress |
| DELETE | `/users/me/skills` | required | none | Clear all tracked skill progress |
| DELETE | `/users/me/skills/{skill_name}` | required | none | Remove one tracked skill |
| GET | `/users/me/history` | required | none | Current user's analysis history |
| GET | `/users/me/feedback` | required | none | Current user's submitted feedback |
| GET | `/health` | none | none | Health check |
| GET | `/metrics/cache` | none | none | In-process cache hit/miss metrics |

"Optional" auth means the endpoint accepts an anonymous caller and also accepts a valid Clerk token if present. "Required" returns 401 without one.

## Database Schema

PostgreSQL, SQLAlchemy models, UUID primary keys throughout:
- `users` — accounts linked to a Clerk identity
- `resumes` — uploaded resumes, parsed sections, active flag
- `job_descriptions` — parsed job requirements
- `ats_analyses` — analysis results, scores, matched/missing skills, evidence, optimized bullets
- `document_chunks` — RAG chunks with pgvector embeddings
- `quiz_results` — generated quizzes and grading
- `skill_progress` — per-user, per-skill quiz progress and resolution state
- `user_feedback` — feedback/suggestion submissions

Two additional tables are defined but not currently used by any route: `analysis_feedback` (a more structured feedback/score-revision model, superseded by `user_feedback`) and `cache_entries` (intended for a DB-backed cache; the live cache is in-memory only).

## Scoring Methodology

```
unified_coverage = (exact_and_normalized_matches + 0.85 × semantic_and_rag_matches) / total_jd_skills
overall_score    = 0.70 × unified_coverage + 0.30 × category_score
```

Category weights: Core 2.0x, Technical 1.5x, Functional 1.2x, Behavioral 0.8x, Supporting 0.6x. See [Hybrid Matching Engine](#hybrid-matching-engine) above for the match-layer order.

## Known Limitations

- **LLM-generated quiz answer keys are not always correct.** The prompt asks the model to independently derive and self-verify each answer before finalizing it, and generation runs at low temperature (0.2) to reduce inconsistency, but this is a mitigation, not a guarantee.
- **Rate limiting is IP-based and in-memory, not distributed.** It uses `slowapi` keyed by client IP with no shared state across backend instances, so it would under-count requests behind a shared IP or across multiple server processes.
- **`GET /analysis/{analysis_id}` and `GET /history` have no authentication or ownership scoping.** Any caller can retrieve any analysis by ID, and `/history` returns analyses across all users rather than filtering by caller. `GET /users/me/history` is the correctly-scoped, authenticated equivalent.
- **Clerk JWT verification does not check the audience claim** (`verify_aud=False`). Signature and expiry are verified; token scoping by audience is not.
- **Unhandled exceptions return the exception type and message directly to the client** (`{"detail": "SomeError: message"}`), which can leak internal error details rather than a generic message.
- **The in-memory cache is single-process.** It does not persist across restarts/deploys and does not share state across multiple backend workers or instances.
- **The evaluation harness in `src/evaluation/evaluator.py` scores against two hardcoded sample resume/JD pairs**, not real analysis history — it's a fixed regression check, not a live quality metric.

## License

MIT
