"""Tunable numbers for the intelligence half."""

from dataclasses import dataclass


@dataclass(frozen=True)
class IntelligenceSettings:
    """Example: `IntelligenceSettings(hint_ttl_seconds=8.0, model_timeout_seconds=2.0)`."""

    hint_ttl_seconds: float = 8.0
    model_timeout_seconds: float = 2.0
