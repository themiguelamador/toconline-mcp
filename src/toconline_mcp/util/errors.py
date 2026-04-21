class TocError(Exception):
    """Base class for TOCOnline MCP errors."""


class AuthError(TocError):
    """Raised when credentials are missing, invalid, or refresh fails."""


class ApiError(TocError):
    """Raised when the TOCOnline API returns an error response."""

    def __init__(self, status: int, message: str, body: object = None):
        super().__init__(f"[{status}] {message}")
        self.status = status
        self.body = body


class ConfigError(TocError):
    """Raised when configuration is missing or invalid."""
