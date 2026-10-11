"""Red-team exception hierarchy."""
from __future__ import annotations


class RedTeamError(Exception):
    """Base class for red-team failures."""


class ReconError(RedTeamError):
    """Raised when the target cannot be reached or fingerprinted."""


class ExploitFailed(RedTeamError):
    """Raised when an exploit module cannot recover a flag."""


class SubmissionError(RedTeamError):
    """Raised when a captured flag is rejected by the scoreboard."""
