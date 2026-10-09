"""UserPromptSubmit: the prompt and the files it provides are origins too (INT-1).

Facts stated in the prompt become User Prompt rows. Files the prompt names (``@notes/q3.md`` or a
plain path that exists in the project) are recorded as provided, so facts later read from them are
Provided Document rows rather than Internal Document. Nothing is added to Claude's context.
"""

import re
from pathlib import Path

from qlaudified import capture, config, paths
from qlaudified.store import Store

_PATHLIKE = re.compile(r"@?((?:[\w.\-]+[/\\])*[\w.\-]+\.[A-Za-z0-9]{1,6})\b")


def provided_files(prompt: str, project, cwd: str | None) -> list[str]:
    out = []
    for m in _PATHLIKE.finditer(prompt):
        name = m.group(1)
        base = cwd or str(project)
        if (Path(base) / name).is_file() or (Path(project) / name).is_file():
            out.append(paths.normalize(name, project, cwd))
    return list(dict.fromkeys(out))


def handle(payload: dict) -> dict | None:
    session_id = payload.get("session_id")
    prompt = payload.get("prompt")
    if not session_id or not isinstance(prompt, str) or not prompt.strip():
        return None
    project = paths.project_dir(payload)
    cfg = config.load(project, session_id)
    turn = payload.get("prompt_id")
    facts = capture.facts_from_passage("user-prompt", "prompt", "prompt", prompt,
                                       payload.get("agent_id") or "main", turn, cfg.lexicon(),
                                       "User Prompt")
    files = provided_files(prompt, project, payload.get("cwd"))
    folder = paths.session_dir(session_id, payload)
    if not facts and not files and not (folder / "index.sqlite").exists():
        return None
    store = Store(folder)
    if files:
        store.add_provided(files, turn)
    if facts:
        step = store.current_step()
        for fact in facts:
            fact.step = step
        store.add_spans(facts)
    store.export_csv()
    return None
