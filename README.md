# AI Job Copilot – ATS Resume Intelligence Platform

A production-grade AI-powered ATS Resume Optimization System featuring retrieval-augmented generation (RAG), hybrid matching, explainable scoring, and continuous evaluation.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        Streamlit UI                              │
│  Dashboard │ Resume │ JD │ Analysis │ Skills │ Optimize │ Quiz  │
└──────────────────────────────┬──────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────┐
│                      FastAPI REST API                            │
│  POST /resume/upload │ POST /job/upload │ POST /analysis/run    │
│  GET /analysis/{id}  │ POST /quiz/start │ GET /history          │
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
│  │  (Relational)  │  │ (Vectors)  │  │  (LRU + Metrics)  │     │
│  └────────────────┘  └────────────┘  └───────────────────┘     │
└─────────────────────────────────────────────────────────────────┘
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Streamlit |
| Backend | Python, FastAPI |
| Database | PostgreSQL + pgvector |
| AI | OpenAI API (GPT-4o-mini, text-embedding-3-small) |
| Deployment | AWS Lambda (via Mangum) |
| CI/CD | GitHub Actions |
| Testing | pytest |

## Key Features

### 1. RAG Pipeline (Real Retrieval-Augmented Generation)
- **Chunking**: Section-aware chunking (512 tokens, 50 token overlap)
- **Embeddings**: OpenAI text-embedding-3-small (1536 dimensions)
- **Storage**: pgvector for vector similarity search
- **Retrieval**: Cosine similarity with configurable threshold

### 2. Hybrid Matching Engine
- **Keyword Matching**: Exact + synonym + phrase matching
- **Semantic Matching**: Embedding-based similarity scoring
- **Category Weighting**: Core skills weighted higher than supporting
- **Formula**: `score = 0.4*keyword + 0.4*semantic + 0.2*category`

### 3. Explainability Layer
Every score includes:
- Why points were awarded
- Why points were deducted
- Which requirements matched (with evidence)
- Which requirements are missing
- Prioritized improvement suggestions

### 4. NLP Classification Pipeline
- Resume/JD parsing with section identification
- LLM-powered skill extraction with validation
- Generic word blocklist (prevents "team", "good" as skills)
- Confidence thresholds (0.6 minimum)
- Skill normalization and deduplication

### 5. Evaluation Framework
- Matching precision/recall/F1 metrics
- Scoring consistency measurement
- Retrieval quality assessment
- Sample evaluation datasets with expected results
- Baseline vs. improved comparison

### 6. Feedback Loop
- Recruiter score adjustments
- Weight tuning
- Historical revision tracking
- Trend analysis (over/under-scoring detection)

### 7. Caching Layer
- LRU cache with TTL expiration
- Tracks: JD parsing, resume parsing, embeddings, analysis results
- Metrics: hit rate, miss rate, latency saved

## Project Structure

```
ai_job_copilot/
├── .github/workflows/ci_cd.yml    # CI/CD pipeline
├── docs/
│   ├── architecture.md            # System architecture
│   └── database_schema.md         # ERD and schema docs
├── src/
│   ├── api/                       # FastAPI REST API
│   │   ├── main.py               # App entry point
│   │   ├── routes/               # Endpoint handlers
│   │   └── schemas/              # Pydantic models
│   ├── core/                      # Config, logging, exceptions
│   ├── database/                  # SQLAlchemy models, session
│   ├── nlp/                       # Parsing, skill extraction
│   ├── rag/                       # Chunking, embeddings, retrieval
│   ├── matching/                  # Scoring engine, explainability
│   ├── evaluation/                # Evaluation framework, feedback
│   ├── cache/                     # Caching with metrics
│   └── ui/                        # Streamlit application
├── tests/
│   ├── unit/                      # Unit tests
│   └── integration/               # API integration tests
├── requirements.txt
├── .env.example
└── README.md
```

## Setup & Installation

### Prerequisites
- Python 3.11+
- PostgreSQL 15+ with pgvector extension
- OpenAI API key

### 1. Clone and Install

```bash
git clone https://github.com/yourusername/ai_job_copilot.git
cd ai_job_copilot
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env with your database URL and OpenAI API key
```

### 3. Initialize Database

```bash
# Ensure PostgreSQL is running with pgvector extension
python -m src.database.init_db
```

### 4. Run the API Server

```bash
uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload
```

### 5. Run the Streamlit UI

```bash
streamlit run src/ui/app.py
```

### 6. Run Tests

```bash
# Unit tests
pytest tests/unit/ -v

# Integration tests
pytest tests/integration/ -v

# All tests with coverage
pytest --cov=src --cov-report=html
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/resume/upload` | Upload and parse a resume |
| POST | `/job/upload` | Upload and parse a job description |
| POST | `/analysis/run` | Run full ATS analysis |
| GET | `/analysis/{id}` | Retrieve analysis results |
| POST | `/quiz/start` | Start skill validation quiz |
| POST | `/quiz/submit` | Submit quiz answers |
| GET | `/history` | Get analysis history |
| GET | `/health` | Health check |
| GET | `/metrics/cache` | Cache performance metrics |

## Database Schema

The system uses a normalized PostgreSQL schema with 9 tables:
- `users` - User accounts
- `resumes` - Uploaded resumes with parsed text
- `job_descriptions` - Job descriptions with requirements
- `skills` - Normalized skill catalog
- `ats_analyses` - Analysis results with scores
- `analysis_skills` - Skill match junction table
- `document_chunks` - RAG chunks with vector embeddings
- `quiz_results` - Skill validation quiz data
- `analysis_feedback` - Feedback loop records
- `cache_entries` - Cache metrics tracking

## Scoring Methodology

```
Overall Score = (0.4 × Keyword Score) + (0.4 × Semantic Score) + (0.2 × Category Score)

Keyword Score = (exact_matches + synonym_matches) / total_required_skills
Semantic Score = (0.6 × coverage) + (0.4 × avg_similarity)
Category Score = weighted_sum(category_match_rates × category_weights)
```

Category weights:
- Core: 2.0x
- Technical: 1.5x
- Functional: 1.2x
- Behavioral: 0.8x
- Supporting: 0.6x

## License

MIT
