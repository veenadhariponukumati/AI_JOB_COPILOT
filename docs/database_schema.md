# Database Schema Documentation

## Entity Relationship Diagram

```mermaid
erDiagram
    USERS ||--o{ RESUMES : owns
    USERS {
        uuid user_id PK
        string email
        datetime created_at
        datetime updated_at
    }

    RESUMES ||--o{ ATS_ANALYSES : evaluated_in
    RESUMES ||--o{ DOCUMENT_CHUNKS : chunked_into
    RESUMES {
        uuid resume_id PK
        uuid user_id FK
        string filename
        text raw_text
        text parsed_text
        json parsed_sections
        datetime upload_timestamp
        datetime updated_at
    }

    JOB_DESCRIPTIONS ||--o{ ATS_ANALYSES : evaluated_against
    JOB_DESCRIPTIONS ||--o{ DOCUMENT_CHUNKS : chunked_into
    JOB_DESCRIPTIONS {
        uuid jd_id PK
        string title
        string company
        text raw_text
        text processed_text
        json parsed_requirements
        datetime upload_timestamp
        datetime updated_at
    }

    SKILLS ||--o{ ANALYSIS_SKILLS : referenced_in
    SKILLS {
        uuid skill_id PK
        string skill_name
        string skill_name_normalized
        enum skill_category
        text description
        json synonyms
        datetime created_at
    }

    ATS_ANALYSES ||--o{ ANALYSIS_SKILLS : contains
    ATS_ANALYSES ||--o{ QUIZ_RESULTS : generates
    ATS_ANALYSES ||--o{ ANALYSIS_FEEDBACK : receives
    ATS_ANALYSES {
        uuid analysis_id PK
        uuid resume_id FK
        uuid jd_id FK
        enum status
        float overall_score
        float keyword_score
        float semantic_score
        json category_scores
        json matched_skills
        json missing_skills
        json recommendations
        json evidence
        json explainability_report
        json optimized_bullets
        int processing_time_ms
        datetime created_at
        datetime updated_at
    }

    ANALYSIS_SKILLS {
        uuid id PK
        uuid analysis_id FK
        uuid skill_id FK
        string source
        float confidence
        string matched
        text evidence_text
    }

    DOCUMENT_CHUNKS {
        uuid chunk_id PK
        uuid resume_id FK
        uuid jd_id FK
        text chunk_text
        int chunk_index
        string section_type
        vector embedding
        json metadata
        datetime created_at
    }

    QUIZ_RESULTS {
        uuid quiz_id PK
        uuid analysis_id FK
        string skill_tested
        json questions
        json answers
        float score
        string passed
        datetime created_at
        datetime completed_at
    }

    ANALYSIS_FEEDBACK {
        uuid feedback_id PK
        uuid analysis_id FK
        string feedback_type
        float original_score
        float revised_score
        json weight_adjustments
        text comments
        datetime created_at
    }

    CACHE_ENTRIES {
        uuid cache_id PK
        string cache_key
        string cache_type
        int hit_count
        int miss_count
        datetime created_at
        datetime last_accessed
        datetime expires_at
    }
```

## Indexing Strategy

| Table | Index Name | Columns | Purpose |
|-------|-----------|---------|---------|
| users | idx_users_email | email | Fast user lookup by email |
| resumes | idx_resumes_user_id | user_id | Retrieve all resumes for a user |
| resumes | idx_resumes_upload_ts | upload_timestamp | Sort by upload date |
| job_descriptions | idx_jd_upload_ts | upload_timestamp | Sort by upload date |
| skills | idx_skills_name | skill_name | Fast skill lookup |
| skills | idx_skills_category | skill_category | Filter by category |
| skills | idx_skills_normalized | skill_name_normalized | Normalized name matching |
| ats_analyses | idx_analysis_resume | resume_id | Find analyses for a resume |
| ats_analyses | idx_analysis_jd | jd_id | Find analyses for a JD |
| ats_analyses | idx_analysis_status | status | Filter by processing status |
| ats_analyses | idx_analysis_created | created_at | Sort by date |
| document_chunks | idx_chunks_resume | resume_id | Find chunks for a resume |
| document_chunks | idx_chunks_jd | jd_id | Find chunks for a JD |
| document_chunks | HNSW on embedding | embedding | Approximate nearest neighbor search |

## Query Optimization Strategy

1. **Connection Pooling**: SQLAlchemy pool with `pool_size=5`, `max_overflow=10`.
2. **Eager Loading**: Use `joinedload` for related entities in common queries.
3. **Pagination**: All list endpoints return paginated results.
4. **Vector Index**: HNSW index on `document_chunks.embedding` for fast ANN queries.
5. **Partial Indexes**: Status-based partial indexes for active analyses.
