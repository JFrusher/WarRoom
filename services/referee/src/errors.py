"""Referee exception hierarchy."""
from __future__ import annotations


class RefereeError(Exception):
    """Base class for referee failures."""


class NoActiveFlagError(RefereeError):
    """Raised when no flag has been minted for the current round."""


class NoActiveRoundError(RefereeError):
    """Raised when an operation needs a running round and none is active."""
