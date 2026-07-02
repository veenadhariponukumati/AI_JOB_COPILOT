"""Retrieval module for the RAG pipeline.

Performs semantic search using pgvector for nearest-neighbor retrieval,
then ranks and filters results by similarity threshold.
"""

from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from src.core.config import get_settings
from src.core.logger import get_logger
from src.core.exceptions import RetrievalError
from src.rag.embedder import EmbeddingGenerator

logger = get_logger(__name__)
settings = get_settings()


class SemanticRetriever:
    """Retrieves relevant document chunks using vector similarity search."""

    def __init__(self, db: Session):
        self.db = db
        self.embedder = EmbeddingGenerator()
        self.top_k = settings.TOP_K_RETRIEVAL
        self.similarity_threshold = settings.SIMILARITY_THRESHOLD

    def retrieve_similar_chunks(
        self,
        query_text: str,
        document_type: Optional[str] = None,
        resume_id: Optional[UUID] = None,
        jd_id: Optional[UUID] = None,
        top_k: Optional[int] = None,
        diagnostics: Optional[Dict[str, Any]] = None,
    ) -> List[Dict]:
        """Retrieve the most similar document chunks for a query.

        Uses cosine similarity via pgvector's <=> operator.

        Args:
            query_text: The query text to find similar chunks for.
            document_type: Filter by 'resume' or 'job_description'.
            resume_id: Filter to specific resume's chunks.
            jd_id: Filter to specific job description's chunks.
            top_k: Override default number of results.

        Returns:
            List of dictionaries with chunk text, similarity score, and metadata.
        """
        k = top_k or self.top_k

        try:
            # Generate query embedding (single - use retrieve_for_analysis for bulk)
            query_embedding = self.embedder.generate_embeddings_batch([query_text])[0]

            # Build the SQL query with pgvector cosine distance
            # pgvector uses <=> for cosine distance (1 - cosine_similarity)
            sql = """
                SELECT
                    chunk_id,
                    chunk_text,
                    section_type,
                    metadata,
                    resume_id,
                    jd_id,
                    1 - (embedding <=> CAST(:query_embedding AS vector)) AS similarity
                FROM document_chunks
                WHERE embedding IS NOT NULL
            """

            params = {"query_embedding": str(query_embedding), "top_k": k}

            # Apply filters
            if resume_id:
                sql += " AND resume_id = :resume_id"
                params["resume_id"] = str(resume_id)
            if jd_id:
                sql += " AND jd_id = :jd_id"
                params["jd_id"] = str(jd_id)
            if document_type:
                sql += " AND metadata->>'document_type' = :doc_type"
                params["doc_type"] = document_type

            if diagnostics is not None and resume_id:
                diagnostics[query_text] = self._build_resume_diagnostics(
                    resume_id=resume_id,
                    query_embedding=query_embedding,
                    top_k=k,
                )

            # Apply similarity threshold and ordering
            sql += """
                AND 1 - (embedding <=> CAST(:query_embedding AS vector)) >= :threshold
                ORDER BY embedding <=> CAST(:query_embedding AS vector) ASC
                LIMIT :top_k
            """
            params["threshold"] = self.similarity_threshold

            result = self.db.execute(text(sql), params)
            rows = result.fetchall()

            chunks = []
            for row in rows:
                chunks.append(
                    {
                        "chunk_id": str(row.chunk_id),
                        "text": row.chunk_text,
                        "section_type": row.section_type,
                        "similarity": round(float(row.similarity), 4),
                        "metadata": row.metadata,
                        "resume_id": str(row.resume_id) if row.resume_id else None,
                        "jd_id": str(row.jd_id) if row.jd_id else None,
                    }
                )

            logger.info(
                f"Retrieved {len(chunks)} chunks (query: {query_text[:50]}..., "
                f"threshold: {self.similarity_threshold})"
            )
            return chunks

        except Exception as e:
            logger.error(f"Retrieval failed: {e}")
            raise RetrievalError(f"Semantic retrieval failed: {str(e)}")

    def retrieve_for_analysis(
        self,
        resume_id: UUID,
        jd_id: UUID,
        query_skills: List[str],
        diagnostics: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, List[Dict]]:
        """Retrieve evidence for a full ATS analysis.

        Batches all skill embeddings into a single OpenAI API call, then
        runs DB queries per skill - avoids N×2 sequential embedding round trips.
        """
        if not query_skills:
            return {}

        # Single batched embedding call for all skills at once
        embeddings = self.embedder.generate_embeddings_batch(query_skills)
        skill_embeddings = dict(zip(query_skills, embeddings))

        evidence_map = {}
        for skill in query_skills:
            query_embedding = skill_embeddings[skill]

            resume_chunks = self._retrieve_with_embedding(
                query_embedding=query_embedding,
                resume_id=resume_id,
                top_k=3,
            )
            jd_chunks = self._retrieve_with_embedding(
                query_embedding=query_embedding,
                jd_id=jd_id,
                top_k=2,
            )

            if diagnostics is not None:
                diagnostics[skill] = self._build_resume_diagnostics(
                    resume_id=resume_id,
                    query_embedding=query_embedding,
                    top_k=3,
                )

            evidence_map[skill] = {
                "resume_evidence": resume_chunks,
                "jd_context": jd_chunks,
                "has_evidence": len(resume_chunks) > 0,
                "max_similarity": (
                    max(c["similarity"] for c in resume_chunks)
                    if resume_chunks
                    else 0.0
                ),
            }

        logger.info(
            f"Retrieved evidence for {len(query_skills)} skills (batched embeddings). "
            f"Found evidence for {sum(1 for v in evidence_map.values() if v['has_evidence'])} skills."
        )
        return evidence_map

    def _retrieve_with_embedding(
        self,
        query_embedding: List[float],
        resume_id: Optional[UUID] = None,
        jd_id: Optional[UUID] = None,
        top_k: int = 3,
    ) -> List[Dict]:
        """Run a pgvector similarity query using a pre-computed embedding."""
        sql = """
            SELECT
                chunk_id, chunk_text, section_type, metadata,
                resume_id, jd_id,
                1 - (embedding <=> CAST(:query_embedding AS vector)) AS similarity
            FROM document_chunks
            WHERE embedding IS NOT NULL
        """
        params: Dict[str, Any] = {
            "query_embedding": str(query_embedding),
            "threshold": self.similarity_threshold,
            "top_k": top_k,
        }
        if resume_id:
            sql += " AND resume_id = :resume_id"
            params["resume_id"] = str(resume_id)
        if jd_id:
            sql += " AND jd_id = :jd_id"
            params["jd_id"] = str(jd_id)
        sql += """
            AND 1 - (embedding <=> CAST(:query_embedding AS vector)) >= :threshold
            ORDER BY embedding <=> CAST(:query_embedding AS vector) ASC
            LIMIT :top_k
        """
        try:
            rows = self.db.execute(text(sql), params).fetchall()
            return [
                {
                    "chunk_id": str(row.chunk_id),
                    "text": row.chunk_text,
                    "section_type": row.section_type,
                    "similarity": round(float(row.similarity), 4),
                    "metadata": row.metadata,
                    "resume_id": str(row.resume_id) if row.resume_id else None,
                    "jd_id": str(row.jd_id) if row.jd_id else None,
                }
                for row in rows
            ]
        except Exception as e:
            logger.error(f"Vector retrieval failed: {e}")
            return []

    def _build_resume_diagnostics(
        self,
        resume_id: UUID,
        query_embedding: List[float],
        top_k: int,
    ) -> Dict[str, Any]:
        """Return threshold-free retrieval diagnostics using an existing query embedding."""
        counts = self.db.execute(
            text(
                """
                SELECT COUNT(*) AS total_chunks, COUNT(embedding) AS non_null_embeddings
                FROM document_chunks
                WHERE resume_id = :resume_id
                """
            ),
            {"resume_id": str(resume_id)},
        ).fetchone()
        rows_exist = self.db.execute(
            text(
                """
                SELECT EXISTS(
                    SELECT 1 FROM document_chunks WHERE resume_id = :resume_id
                ) AS rows_exist
                """
            ),
            {"resume_id": str(resume_id)},
        ).scalar()
        rows = self.db.execute(
            text(
                """
                SELECT
                    chunk_id,
                    chunk_text,
                    section_type,
                    1 - (embedding <=> CAST(:query_embedding AS vector)) AS similarity
                FROM document_chunks
                WHERE resume_id = :resume_id AND embedding IS NOT NULL
                ORDER BY embedding <=> CAST(:query_embedding AS vector) ASC
                LIMIT :top_k
                """
            ),
            {
                "resume_id": str(resume_id),
                "query_embedding": str(query_embedding),
                "top_k": top_k,
            },
        ).fetchall()

        return {
            "resume_id": str(resume_id),
            "chunk_count": int(counts.total_chunks),
            "non_null_embedding_count": int(counts.non_null_embeddings),
            "rows_exist_after_resume_id_filter": bool(rows_exist),
            "threshold": self.similarity_threshold,
            "top_similarities_without_threshold": [
                {
                    "chunk_id": str(row.chunk_id),
                    "section_type": row.section_type,
                    "similarity": round(float(row.similarity), 4),
                    "snippet": str(row.chunk_text or "")[:240],
                }
                for row in rows
            ],
        }

    def get_retrieval_stats(self) -> Dict:
        """Get retrieval statistics for monitoring."""
        try:
            result = self.db.execute(
                text("SELECT COUNT(*) as total FROM document_chunks WHERE embedding IS NOT NULL")
            )
            total_chunks = result.scalar()

            return {
                "total_indexed_chunks": total_chunks,
                "embedding_dimensions": settings.OPENAI_EMBEDDING_DIMENSIONS,
                "similarity_threshold": self.similarity_threshold,
                "top_k": self.top_k,
            }
        except Exception:
            return {"error": "Could not retrieve stats"}
