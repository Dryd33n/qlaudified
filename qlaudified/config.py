"""Project config in ``config.toml``: mode, backend, budgets, lexicon overrides (MOD-2, CFG-1, CFG-2).

Sprint 1. Reading uses ``tomllib`` (3.11+) with a minimal fallback parser for 3.10.
"""

from dataclasses import dataclass, field
from enum import Enum


class Mode(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class Config:
    mode: Mode = Mode.MEDIUM
    backend: str = "claude-cli"  # claude-cli | ollama | none | fake (tests only)
    backend_model: str = "haiku"  # default small model: decided from Sprint 0 timings
    python: str = "python"  # or "py -3" on Windows
    inject_budget_chars: int = 600  # INJ-2
    critical_threshold: float = 0.5  # CFG-2, tuned in Sprint 2
    extra_hedges: dict[str, list[str]] = field(default_factory=dict)
    retention_days: int = 30
    raw_cache_mb: int = 200


def load(project_dir) -> Config:
    """Load config with defaults; apply a one-session override if set (MOD-3)."""
    raise NotImplementedError("Sprint 1: MOD-1..3")


def save_mode(project_dir, mode: Mode) -> None:
    raise NotImplementedError("Sprint 1: MOD-1, MOD-2")
