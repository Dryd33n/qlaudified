"""Project config in ``config.toml``: mode, backend, budgets, lexicon overrides (MOD-1..3, CFG-1, CFG-2).

``config.toml`` lives in the store root and is read with ``tomllib``. A one-session mode override
lives in that session's folder, so it never changes the saved default (MOD-3). Loading never
raises: a missing or broken file gives the defaults, and the problem is kept in ``Config.problems``.
"""

import re
from enum import StrEnum
from pathlib import Path

from qlaudified import NAME, lexicon
from qlaudified.paths import ensure_gitignore, safe_name
from qlaudified.records import record


class Mode(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@record
class Config:
    mode: Mode = Mode.MEDIUM
    backend: str = "claude-cli"  # claude-cli | ollama | none | fake (tests only)
    backend_model: str = "haiku"  # Sprint 0: ~2.6 s per call, 15x cheaper than sonnet
    inject_budget_chars: int = 600  # INJ-2, per PostToolUse call
    digest_budget_chars: int = 1200  # INJ-3, once after each compaction
    critical_threshold: float = 0.5  # CFG-2, tuned in Sprint 2
    extra_hedges: dict[str, list[str]] = {}  # noqa: RUF012 - @record copies it per instance
    retention_days: int = 30
    raw_cache_mb: int = 200
    mode_source: str = "default"  # default | config | session
    refeed: str = "full"  # full | placebo (study control: refeed lines without qualifiers)
    problems: list[str] = []  # noqa: RUF012 - @record copies it per instance

    def lexicon(self) -> dict[str, list[str]]:
        return lexicon.merged(self.extra_hedges)


TEMPLATE = """\
# qlaudified settings for this project. Delete a line to get the default back.
mode = "medium"            # low | medium | high
backend = "claude-cli"     # claude-cli | ollama | none
backend_model = "haiku"
inject_budget_chars = 600
digest_budget_chars = 1200
critical_threshold = 0.5
retention_days = 30
raw_cache_mb = 200

[hedges]                   # extra hedge words, by class (modal, estimate, attribution, ...)
# estimate = ["ballpark"]
"""

_TYPES: dict[str, type | tuple[type, ...]] = {
    "backend": str, "backend_model": str, "inject_budget_chars": int, "digest_budget_chars": int,
    "critical_threshold": (int, float), "retention_days": int, "raw_cache_mb": int, "refeed": str,
}
REFEED = ("full", "placebo")


def store_dir(project_dir) -> Path:
    return Path(project_dir) / ".claude" / f".{NAME}"


def config_path(project_dir) -> Path:
    return store_dir(project_dir) / "config.toml"


def _session_mode_path(project_dir, session_id: str) -> Path:
    return store_dir(project_dir) / "sessions" / safe_name(session_id) / "mode"


def load(project_dir, session_id: str | None = None) -> Config:
    """Load config with defaults; apply a one-session override if set (MOD-3)."""
    cfg = Config()
    path = config_path(project_dir)
    data: dict = {}
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        text = None
    except (OSError, UnicodeDecodeError) as e:
        text = None
        cfg.problems.append(f"{path.name}: {e}")
    if text is not None:
        import tomllib  # only when there is a file: the import costs ~12 ms per hook call

        try:
            data = tomllib.loads(text)
        except tomllib.TOMLDecodeError as e:
            cfg.problems.append(f"{path.name}: {e}")

    if "mode" in data:
        try:
            cfg.mode, cfg.mode_source = Mode(str(data["mode"]).lower()), "config"
        except ValueError:
            cfg.problems.append(f"unknown mode {data['mode']!r}; using {cfg.mode}")
    for key, kind in _TYPES.items():
        if key in data:
            if isinstance(data[key], kind) and not isinstance(data[key], bool):
                setattr(cfg, key, data[key])
            else:
                cfg.problems.append(f"{key}: expected {kind}, got {data[key]!r}")
    if cfg.refeed not in REFEED:
        cfg.problems.append(f"refeed: expected one of {', '.join(REFEED)}, got {cfg.refeed!r}")
        cfg.refeed = "full"
    hedges = data.get("hedges", {})
    if isinstance(hedges, dict):
        cfg.extra_hedges = {
            str(k): [str(w) for w in v] for k, v in hedges.items() if isinstance(v, list)
        }

    if session_id:
        override = session_mode(project_dir, session_id)
        if override is not None:
            cfg.mode, cfg.mode_source = override, "session"
    return cfg


def save_mode(project_dir, mode: Mode) -> None:
    """Persist the project's default mode (MOD-1, MOD-2), keeping the rest of the file as is."""
    path = config_path(project_dir)
    ensure_gitignore(path.parent)
    text = path.read_text(encoding="utf-8") if path.exists() else TEMPLATE
    line = f'mode = "{Mode(mode)}"'
    pattern = re.compile(r'^mode\s*=\s*"[^"\n]*"', re.MULTILINE)
    text = pattern.sub(line, text, count=1) if pattern.search(text) else f"{line}\n{text}"
    path.write_text(text, encoding="utf-8")


def session_mode(project_dir, session_id: str) -> Mode | None:
    try:
        return Mode(_session_mode_path(project_dir, session_id).read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def set_session_mode(project_dir, session_id: str, mode: Mode | None) -> None:
    """Override the mode for one session only (MOD-3); ``None`` clears the override."""
    path = _session_mode_path(project_dir, session_id)
    if mode is None:
        path.unlink(missing_ok=True)
        return
    ensure_gitignore(store_dir(project_dir))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(Mode(mode)), encoding="utf-8")
