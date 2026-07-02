"""Embedding generation module for the RAG pipeline.

Generates vector embeddings using OpenAI's text-embedding-3-small model
and stores them in PostgreSQL with pgvector.
"""

import hashlib
from typing import List

from openai import OpenAI

from src.core.config import get_settings
from src.core.exceptions import EmbeddingError
from src.core.logger import get_logger

logger = get_logger(__name__)
settings = get_settings()


class EmbeddingGenerator:
    """Generates and manages text embeddings using OpenAI API."""

    def __init__(self):
        self.client = OpenAI(
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_API_BASE if settings.OPENAI_API_BASE else None,
        )
        self.model = settings.OPENAI_EMBEDDING_MODEL
        self.dimensions = settings.OPENAI_EMBEDDING_DIMENSIONS

    def generate_embedding(self, text: str) -> List[float]:
        """Generate a single embedding vector for text.

        Args:
            text: Input text to embed.

        Returns:
            List of floats representing the embedding vector.
        """
        if not text or not text.strip():
            raise EmbeddingError("Cannot generate embedding for empty text")

        try:
            # Truncate to model's max input (8191 tokens ~ 32000 chars)
            truncated = text[:32000] if len(text) > 32000 else text

            response = self.client.embeddings.create(
                model=self.model,
                input=truncated,
            )

            embedding = response.data[0].embedding
            logger.debug(f"Generated embedding: {len(embedding)} dimensions")
            return embedding

        except Exception as e:
            logger.error(f"Embedding generation failed: {e}")
            raise EmbeddingError(f"Failed to generate embedding: {str(e)}")

    def generate_embeddings_batch(self, texts: List[str], batch_size: int = 20) -> List[List[float]]:
        """Generate embeddings for multiple texts in batches.

        Args:
            texts: List of input texts.
            batch_size: Number of texts per API call.

        Returns:
            List of embedding vectors (same order as input).
        """
        if not texts:
            return []

        all_embeddings = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            # Truncate each text
            batch = [t[:32000] if len(t) > 32000 else t for t in batch]
            # Filter empty texts
            batch = [t if t.strip() else "empty" for t in batch]

            try:
                response = self.client.embeddings.create(
                    model=self.model,
                    input=batch,
                )

                batch_embeddings = [item.embedding for item in response.data]
                all_embeddings.extend(batch_embeddings)

                logger.debug(
                    f"Generated batch embeddings: {len(batch_embeddings)} vectors " f"(batch {i // batch_size + 1})"
                )

            except Exception as e:
                logger.error(f"Batch embedding failed at index {i}: {e}")
                raise EmbeddingError(f"Batch embedding generation failed: {str(e)}")

        return all_embeddings

    def compute_text_hash(self, text: str) -> str:
        """Compute a hash for cache key generation.

        Args:
            text: Input text.

        Returns:
            SHA-256 hex digest of the text.
        """
        return hashlib.sha256(text.encode("utf-8")).hexdigest()
