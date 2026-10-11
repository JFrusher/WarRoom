"""Custom exception hierarchy for the target application."""
from __future__ import annotations


class TargetAppError(Exception):
    """Base class for all application-specific errors."""


class FlagUnavailableError(TargetAppError):
    """Raised when the current flag cannot be read from storage."""


class DiagnosticsError(TargetAppError):
    """Raised when a diagnostics command cannot be executed."""


class RateLimitedError(TargetAppError):
    """Raised when a client IP has been blocked by the blue team."""
