"""Document chunking module for the RAG pipeline.

Implements intelligent chunking with configurable size and overlap.

Chunking Strategy:
- Chunk Size: 512 tokens (~2000 chars) - balances context richness with retrieval precision
- Chunk Overlap: 50 tokens (~200 chars) - prevents information loss at boundaries
- Section-aware: Respects document section boundaries when possible

Rationale:
- 512 tokens provides enough context for meaningful semantic matching
- Overlap ensures skills/requirements spanning chunk boundaries are captured
- Section-aware chunking preserves logical groupings (e.g., all skills together)
"""

import re
from typing import Dict, List, Optional

from src.core.config import get_settings
from src.core.logger import get_logger

logger = get_logger(__name__)
settings = get_settings()

# Approximate chars per token ratio (for English text)
CHARS_PER_TOKEN = 4


class DocumentChunker:
    """Chunks documents for embedding and retrieval."""

    def __init__(
        self,
        chunk_size: int = None,
        chunk_overlap: int = None,
    ):
        """Initialize chunker with configurable parameters.

        Args:
            chunk_size: Target chunk size in tokens (default from settings).
            chunk_overlap: Overlap between chunks in tokens (default from settings).
        """
        self.chunk_size = chunk_size or settings.CHUNK_SIZE
        self.chunk_overlap = chunk_overlap or settings.CHUNK_OVERLAP
        self.chunk_size_chars = self.chunk_size * CHARS_PER_TOKEN
        self.chunk_overlap_chars = self.chunk_overlap * CHARS_PER_TOKEN

    def chunk_document(
        self,
        text: str,
        sections: Optional[Dict[str, str]] = None,
        document_type: str = "resume",
    ) -> List[Dict]:
        """Chunk a document into overlapping segments.

        If sections are provided, chunks respect section boundaries.
        Otherwise, falls back to character-based chunking with overlap.

        Args:
            text: Full document text.
            sections: Optional dict of section_name -> section_text.
            document_type: 'resume' or 'job_description'.

        Returns:
            List of chunk dictionaries with text, index, section_type, metadata.
        """
        if sections and len(sections) > 1:
            chunks = self._chunk_by_sections(sections, document_type)
        else:
            chunks = self._chunk_by_characters(text, document_type)

        logger.info(
            f"Chunked {document_type}: {len(chunks)} chunks " f"(size={self.chunk_size}, overlap={self.chunk_overlap})"
        )
        return chunks

    def _chunk_by_sections(self, sections: Dict[str, str], document_type: str) -> List[Dict]:
        """Chunk document respecting section boundaries.

        Each section is chunked independently, preserving logical groupings.
        """
        all_chunks = []
        chunk_index = 0

        for section_name, section_text in sections.items():
            if not section_text or len(section_text.strip()) < 20:
                continue

            # If section fits in one chunk, keep it whole
            if len(section_text) <= self.chunk_size_chars:
                all_chunks.append(
                    {
                        "text": section_text.strip(),
                        "index": chunk_index,
                        "section_type": section_name,
                        "metadata": {
                            "document_type": document_type,
                            "char_count": len(section_text),
                            "is_complete_section": True,
                        },
                    }
                )
                chunk_index += 1
            else:
                # Split large sections with overlap
                section_chunks = self._split_with_overlap(section_text)
                for i, chunk_text in enumerate(section_chunks):
                    all_chunks.append(
                        {
                            "text": chunk_text.strip(),
                            "index": chunk_index,
                            "section_type": section_name,
                            "metadata": {
                                "document_type": document_type,
                                "char_count": len(chunk_text),
                                "section_part": i + 1,
                                "section_total_parts": len(section_chunks),
                                "is_complete_section": False,
                            },
                        }
                    )
                    chunk_index += 1

        return all_chunks

    def _chunk_by_characters(self, text: str, document_type: str) -> List[Dict]:
        """Fallback character-based chunking with overlap."""
        chunks = []
        text_chunks = self._split_with_overlap(text)

        for i, chunk_text in enumerate(text_chunks):
            chunks.append(
                {
                    "text": chunk_text.strip(),
                    "index": i,
                    "section_type": "unknown",
                    "metadata": {
                        "document_type": document_type,
                        "char_count": len(chunk_text),
                    },
                }
            )

        return chunks

    def _split_with_overlap(self, text: str) -> List[str]:
        """Split text into overlapping chunks at sentence boundaries.

        Tries to split at sentence endings to preserve meaning.
        """
        chunks = []
        start = 0
        text_len = len(text)

        while start < text_len:
            end = start + self.chunk_size_chars

            if end >= text_len:
                # Last chunk
                chunk = text[start:]
                if chunk.strip():
                    chunks.append(chunk)
                break

            # Try to find a sentence boundary near the end
            boundary = self._find_sentence_boundary(text, end)
            if boundary and boundary > start:
                end = boundary

            chunk = text[start:end]
            if chunk.strip():
                chunks.append(chunk)

            # Move start forward with overlap
            start = end - self.chunk_overlap_chars
            if start <= chunks[-1] if not chunks else 0:
                start = end  # Prevent infinite loop

        return chunks

    def _find_sentence_boundary(self, text: str, target_pos: int, search_range: int = 100) -> Optional[int]:
        """Find the nearest sentence boundary near target_pos.

        Looks for period, question mark, or exclamation followed by space/newline.
        """
        search_start = max(0, target_pos - search_range)
        search_end = min(len(text), target_pos + search_range)
        search_text = text[search_start:search_end]

        # Find sentence-ending patterns
        boundaries = []
        for match in re.finditer(r"[.!?]\s", search_text):
            abs_pos = search_start + match.end()
            boundaries.append(abs_pos)

        # Also consider newlines as boundaries
        for match in re.finditer(r"\n", search_text):
            abs_pos = search_start + match.end()
            boundaries.append(abs_pos)

        if not boundaries:
            return None

        # Return the boundary closest to target_pos
        return min(boundaries, key=lambda x: abs(x - target_pos))
