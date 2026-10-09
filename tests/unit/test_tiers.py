"""Model tiers and backends with no model calls: tier 3 batching and validation, the claude-cli and
Ollama backends against stand-ins, and the NLI tier when its model is installed (VER-3, CFG-1, SID-3)."""

import json
import os
import subprocess
import sys

import pytest

from qlaudified.backends.claude_cli import ClaudeCliBackend
from qlaudified.backends.fake import FakeBackend
from qlaudified.backends.ollama import OllamaBackend
from qlaudified.config import Config
from qlaudified.store import Span, Turn
from qlaudified.verify import tier3_llm, verify_answer

PAGE = Span("S1", "local-doc", "ops.md", "L2", "Deploys go out on Tuesdays after QA signs off.",
            hash="a")
MEMO = Span("S2", "local-doc", "memo.md", "L1", "The QA team is staffed by two contractors.",
            hash="b")


def test_prompt_lists_each_claim_with_only_its_passages():
    prompt = tier3_llm.build_prompt([tier3_llm.item("C1.1", "Deploys are weekly.", [PAGE])])
    assert "Claim C1.1: Deploys are weekly." in prompt
    assert "[S1] (ops.md L2) Deploys go out on Tuesdays" in prompt
    assert "MEMO" not in prompt and "S2" not in prompt


def test_invalid_answers_leave_claims_alone_and_unknown_ids_are_dropped():
    items = [tier3_llm.item("C1.1", "a", [PAGE]), tier3_llm.item("C1.2", "b", [MEMO])]
    fake = FakeBackend([{"verdicts": [
        {"id": "C1.1", "verdict": "supported", "span_ids": ["S1", "S7"], "dropped_qualifiers": ["x"],
         "confidence": 3},
        {"id": "C1.2", "verdict": "made-up"},
    ]}])
    first, second = tier3_llm.check_batch(items, fake)
    assert first == {"verdict": "supported", "span_ids": ["S1"], "dropped_qualifiers": [],
                     "decided_by": "llm", "confidence": 1.0}
    assert second is None
    assert tier3_llm.check_batch(items, FakeBackend([])) == [None, None]  # backend failed


def test_only_undecided_claims_reach_the_llm_in_one_call():
    spans = [PAGE, MEMO, Span("S3", "local-doc", "q3.md", "L3", "Q3 revenue is estimated at $4.2M.",
                              "4200000 USD", "estimated", hash="c")]
    fake = FakeBackend([{"verdicts": [{"id": "C1.2", "verdict": "inference", "span_ids": ["S1"],
                                       "dropped_qualifiers": [], "confidence": 0.6}]}])
    answer = "Q3 revenue was $4.2M. Deploys at Fernwick happen weekly once testing approves."
    claims, _ = verify_answer(answer, spans, Turn(1, "p", answer, ""), Config(), fake)
    assert [(c.verdict, c.decided_by) for c in claims] == [
        ("qualifier-dropped", "deterministic"), ("inference", "llm")]
    assert len(fake.prompts) == 1 and "C1.1" not in fake.prompts[0]


def test_claude_cli_backend_runs_a_tool_less_safe_mode_call(monkeypatch):
    seen = {}

    def run(cmd, **kwargs):
        seen.update(cmd=cmd, **kwargs)
        out = {"structured_output": {"verdicts": []}, "total_cost_usd": 0.0008, "is_error": False,
               "usage": {"input_tokens": 2, "cache_creation_input_tokens": 3594, "output_tokens": 9}}
        return subprocess.CompletedProcess(cmd, 0, json.dumps(out).encode(), b"")

    monkeypatch.setattr("shutil.which", lambda name: "claude.exe")
    monkeypatch.setattr(subprocess, "run", run)
    backend = ClaudeCliBackend("haiku")
    assert backend.complete_json("prompt", tier3_llm.SCHEMA) == {"verdicts": []}
    cmd = seen["cmd"]
    assert cmd[:2] == ["claude.exe", "-p"] and "--safe-mode" in cmd
    assert cmd[cmd.index("--tools") + 1] == "" and "--no-session-persistence" in cmd
    assert json.loads(cmd[cmd.index("--json-schema") + 1]) == tier3_llm.SCHEMA
    assert seen["env"]["QLAUDIFIED_NESTED"] == "1" and seen["input"] == b"prompt"
    assert backend.last_usage["cost_usd"] == 0.0008 and backend.last_usage["input_tokens"] == 3596


def test_claude_cli_backend_reports_failures_as_none(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: None)
    backend = ClaudeCliBackend("haiku")
    assert backend.complete_json("p", {}) is None and "not found" in backend.last_usage["error"]


def test_ollama_backend_sends_the_schema_as_format():
    import http.server
    import threading

    got = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            got.update(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            body = json.dumps({"message": {"content": '{"verdicts": []}'},
                               "prompt_eval_count": 40, "eval_count": 5}).encode()
            self.send_response(200)
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.handle_request, daemon=True).start()
    backend = OllamaBackend("qwen2.5:7b", f"http://127.0.0.1:{server.server_address[1]}")
    assert backend.complete_json("prompt", tier3_llm.SCHEMA) == {"verdicts": []}
    assert got["format"] == tier3_llm.SCHEMA and got["model"] == "qwen2.5:7b"
    assert OllamaBackend("m", "http://127.0.0.1:9").complete_json("p", {}) is None


def test_nested_calls_never_run_our_hooks(repo, tmp_path):
    proc = subprocess.run([sys.executable, str(repo / "hooks" / "run.py"), "PostToolUse"],
                          input=b'{"session_id": "s", "tool_name": "Read"}', capture_output=True,
                          env={**os.environ, "QLAUDIFIED_NESTED": "1",
                               "CLAUDE_PROJECT_DIR": str(tmp_path)}, check=False)
    assert proc.returncode == 0 and proc.stdout == b"" and not (tmp_path / ".claude").exists()


@pytest.fixture
def real_nli(monkeypatch):
    from conftest import REAL_CACHE

    from qlaudified.verify import tier2_nli

    monkeypatch.setenv("QLAUDIFIED_CACHE", REAL_CACHE)
    if not tier2_nli.available():
        pytest.skip("NLI extra or model not installed (/qlaudified nli install)")
    return tier2_nli


def test_nli_decides_paraphrases_the_rules_cannot(real_nli):
    assert real_nli.check("Deployments happen after quality assurance approves them.",
                          [PAGE])["verdict"] == "supported"
    assert real_nli.check("Deploys go out before QA has looked at them.",
                          [PAGE])["verdict"] == "contradicted"
    assert real_nli.check("The office has a rooftop garden.", [PAGE]) is None
    hedged = Span("S4", "local-doc", "ops.md", "L3", "Hotfixes may skip the Tuesday window.",
                  hash="d")
    # A dropped "may" reads as neutral, not entailed: NLI leaves it to the rules and the LLM.
    assert real_nli.check("Hotfixes skip the Tuesday deploy window.", [hedged]) is None


def test_tier_labels_cover_every_decider():
    from qlaudified.report import TIERS

    assert set(TIERS) == {"deterministic", "nli", "llm", "reread"}


def test_nli_ignores_search_titles(real_nli):
    title = Span("S5", "search-snippet", "https://example.org/x", "title",
                 "sqlite3 connect parameter check_same_thread not documented", hash="e")
    assert real_nli.check("Setting check_same_thread=False allows multi-thread access.",
                          [title]) is None
