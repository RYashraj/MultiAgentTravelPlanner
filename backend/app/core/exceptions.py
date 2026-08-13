from typing import Any, Dict, Optional

class VoyagerError(Exception):
    """Base exception for VoyagerAI."""
    def __init__(self, message: str, status_code: int = 500, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.details = details or {}

class RateLimitExceeded(VoyagerError):
    """Raised when a user exceeds their rate limit."""
    def __init__(self, message: str = "Rate limit exceeded", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, status_code=429, details=details)

class ValidationError(VoyagerError):
    """Raised for input validation failures beyond Pydantic."""
    def __init__(self, message: str = "Validation error", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, status_code=422, details=details)

class AgentError(VoyagerError):
    """Raised when an AI agent fails to complete its task."""
    def __init__(self, message: str = "Agent execution failed", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, status_code=500, details=details)
