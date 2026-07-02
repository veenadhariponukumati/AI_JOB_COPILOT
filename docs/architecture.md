# AI Job Copilot Architecture

## 1. System Overview

The AI Job Copilot is a production-grade ATS Resume Optimization System. It uses a retrieval-augmented generation (RAG) approach to evaluate resumes against job descriptions, providing an explainable scoring mechanism, skill gap analysis, and resume optimization suggestions.

## 2. Architecture Diagram

```mermaid
graph TD
    User([User]) --> UI[Streamlit UI]
    UI --> API[FastAPI REST API]
    
    API --> Controller[Core Logic / Orchestrator]
    
    Controller --> NLP[NLP Pipeline]
    Controller --> RAG[RAG Pipeline]
    Controller --> Matcher[Hybrid Matching Engine]
    
    NLP --> Parser[Document Parser]
    NLP --> Extractor[Skill Extractor]
    NLP --> LLM[OpenAI API]
    
    RAG --> Embedder[Embedding Generator]
    RAG --> VectorDB[(pgvector)]
    
    Matcher --> DB[(PostgreSQL)]
    Matcher --> Explainer[Explainability Layer]
    
    subgraph Data Layer
        DB
        VectorDB
        Cache[(Local/In-Memory Cache)]
    end
```

## 3. Data Flow Diagram

```mermaid
sequenceDiagram
    participant User
    participant UI as Streamlit UI
    participant API as FastAPI
    participant NLP as NLP Pipeline
    participant DB as PostgreSQL/pgvector
    participant Matcher as Matching Engine
    participant LLM as OpenAI API

    User->>UI: Upload Resume & Job Description
    UI->>API: POST /analysis/run
    API->>NLP: Parse Documents
    NLP->>DB: Store Raw Text
    NLP->>LLM: Extract Skills & Classify
    LLM-->>NLP: Structured Skills
    NLP->>DB: Store Extracted Skills
    API->>Matcher: Run Hybrid Matching
    Matcher->>DB: Retrieve Vector Embeddings
    Matcher->>Matcher: Calculate Similarity & Keyword Match
    Matcher->>LLM: Generate Explainability Report
    LLM-->>Matcher: Evidence & Explanations
    Matcher->>DB: Save Analysis Results
    Matcher-->>API: Return Final Score & Report
    API-->>UI: Display Results
    UI-->>User: Show ATS Score & Feedback
```

## 4. Folder Structure

```
ai_job_copilot/
├── .github/
│   └── workflows/
│       └── ci_cd.yml
├── docs/
│   ├── architecture.md
│   └── database_schema.md
├── src/
│   ├── api/                 # FastAPI routes and schemas
│   │   ├── routes/
│   │   └── schemas/
│   ├── core/                # Business logic
│   │   ├── config.py
│   │   ├── exceptions.py
│   │   └── logger.py
│   ├── database/            # SQLAlchemy models and migrations
│   │   ├── models.py
│   │   └── session.py
│   ├── nlp/                 # Parsing and extraction
│   │   ├── parser.py
│   │   └── extractor.py
│   ├── rag/                 # Chunking, embeddings, retrieval
│   │   ├── chunker.py
│   │   ├── embedder.py
│   │   └── retriever.py
│   ├── matching/            # Scoring and explainability
│   │   ├── engine.py
│   │   └── explainer.py
│   ├── evaluation/          # Testing framework for AI outputs
│   └── ui/                  # Streamlit application
│       ├── pages/
│       └── app.py
├── tests/
│   ├── unit/
│   └── integration/
├── .env
├── .gitignore
├── requirements.txt
└── README.md
```

## 5. Deployment Architecture

- **Frontend**: Streamlit (can be deployed on Streamlit Community Cloud or AWS EC2/ECS)
- **Backend API**: FastAPI deployed on AWS Lambda (via Mangum) or AWS ECS/AppRunner.
- **Database**: Amazon RDS for PostgreSQL with the `pgvector` extension enabled.
- **AI Services**: OpenAI API for LLM and Embeddings.
- **CI/CD**: GitHub Actions for automated testing and deployment.
