"""Custom application exceptions."""


class AppException(Exception):
    """Base application exception."""

    def __init__(self, message: str, status_code: int = 500):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


class ParsingError(AppException):
    """Raised when document parsing fails."""

    def __init__(self, message: str = "Failed to parse document"):
        super().__init__(message, status_code=422)


class ExtractionError(AppException):
    """Raised when skill extraction fails."""

    def __init__(self, message: str = "Failed to extract skills"):
        super().__init__(message, status_code=422)


class EmbeddingError(AppException):
    """Raised when embedding generation fails."""

    def __init__(self, message: str = "Failed to generate embeddings"):
        super().__init__(message, status_code=500)


class RetrievalError(AppException):
    """Raised when RAG retrieval fails."""

    def __init__(self, message: str = "Failed to retrieve relevant context"):
        super().__init__(message, status_code=500)


class AnalysisError(AppException):
    """Raised when ATS analysis fails."""

    def __init__(self, message: str = "Failed to run analysis"):
        super().__init__(message, status_code=500)


class DatabaseError(AppException):
    """Raised when database operations fail."""

    def __init__(self, message: str = "Database operation failed"):
        super().__init__(message, status_code=500)


class ValidationError(AppException):
    """Raised when input validation fails."""

    def __init__(self, message: str = "Validation failed"):
        super().__init__(message, status_code=400)
