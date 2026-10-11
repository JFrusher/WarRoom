"""Blue-team exception hierarchy."""
from __future__ import annotations


class BlueTeamError(Exception):
    """Base class for blue-team failures."""


class LogUnavailableError(BlueTeamError):
    """Raised when the application log cannot be opened for tailing."""
