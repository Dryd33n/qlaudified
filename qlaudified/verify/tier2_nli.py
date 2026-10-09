"""Optional NLI tier: DeBERTa-v3-xsmall MNLI on ONNX Runtime CPU, behind the [nli] extra (VER-3).

Runs only on claims Tier 1 left undecided. Each candidate passage is a premise and the claim the
hypothesis; strong entailment means supported (or qualifier-dropped, when the passage is hedged and
the claim isn't), strong contradiction means contradicted, anything in between moves on.

The model (~87 MB, quantized) is downloaded once with ``/qlaudified nli install`` into
``~/.cache/qlaudified/<MODEL_NAME>/``. Without the extra or the model, the tier is skipped.
"""

import json
import os
import urllib.request
from pathlib import Path

from qlaudified import indexer, text
from qlaudified.store import Span

MODEL_REPO = "Xenova/nli-deberta-v3-xsmall"
MODEL_NAME = "nli-deberta-v3-xsmall"
FILES = {"config.json": "config.json", "tokenizer.json": "tokenizer.json",
         "model.onnx": "onnx/model_quantized.onnx"}
ENTAIL = 0.80  # borderline thresholds: below these the claim moves on to tier 3
CONTRADICT = 0.80
MAX_TOKENS = 256
MIN_OVERLAP = 0.3  # a premise must share some words with the claim to be worth comparing


def model_dir() -> Path:
    base = os.environ.get("QLAUDIFIED_CACHE") or Path.home() / ".cache" / "qlaudified"
    return Path(base) / MODEL_NAME


def available() -> bool:
    """The model is downloaded and the extra installed. Hooks run with ``python -S`` (no
    site-packages, ~50 ms faster), so site-packages is added here, only when the model exists."""
    if not all((model_dir() / name).exists() for name in FILES):
        return False
    import sys

    if sys.flags.no_site:
        import site

        site.main()
    try:
        import numpy  # noqa: F401
        import onnxruntime  # noqa: F401
        import tokenizers  # noqa: F401
    except ImportError:
        return False
    return True


def install(progress=print) -> Path:
    """Download the model files from Hugging Face (one time)."""
    folder = model_dir()
    folder.mkdir(parents=True, exist_ok=True)
    for name, remote in FILES.items():
        target = folder / name
        if target.exists():
            continue
        url = f"https://huggingface.co/{MODEL_REPO}/resolve/main/{remote}"
        progress(f"downloading {url}")
        tmp = target.with_suffix(".part")
        urllib.request.urlretrieve(url, tmp)
        tmp.replace(target)
    return folder


class NLI:
    def __init__(self, folder: Path) -> None:
        import onnxruntime
        from tokenizers import Tokenizer

        self.session = onnxruntime.InferenceSession(str(folder / "model.onnx"),
                                                    providers=["CPUExecutionProvider"])
        self.inputs = {i.name for i in self.session.get_inputs()}
        self.tokenizer = Tokenizer.from_file(str(folder / "tokenizer.json"))
        self.tokenizer.enable_truncation(MAX_TOKENS)
        labels = json.loads((folder / "config.json").read_text(encoding="utf-8"))["id2label"]
        self.labels = [labels[str(i)].lower() for i in range(len(labels))]

    def scores(self, premise: str, hypothesis: str) -> dict[str, float]:
        import numpy as np

        enc = self.tokenizer.encode(premise, hypothesis)
        feed = {
            "input_ids": np.array([enc.ids], dtype=np.int64),
            "attention_mask": np.array([enc.attention_mask], dtype=np.int64),
            "token_type_ids": np.array([enc.type_ids], dtype=np.int64),
        }
        logits = self.session.run(None, {k: v for k, v in feed.items() if k in self.inputs})[0][0]
        exp = np.exp(logits - logits.max())
        probs = exp / exp.sum()
        return {label: float(p) for label, p in zip(self.labels, probs, strict=True)}

    def check(self, claim: str, spans: list[Span]) -> dict | None:
        from qlaudified.verify.tier1 import missing_qualifiers

        hypothesis = text.clean(claim)
        claim_tokens = text.tokens(hypothesis)
        best: tuple[float, str, Span, str] | None = None
        # Search titles aren't statements: live, a title "parameter not documented" came out as
        # contradicting a claim about what the parameter does.
        for span in (s for s in spans if s.origin != "search-snippet"):
            for unit in text.units(span.text) or [span.text]:
                s = self.scores(unit, hypothesis)
                # Paraphrases may share no words, but a contradiction must be on the same topic.
                if text.coverage(claim_tokens, text.tokens(text.clean(unit))) < MIN_OVERLAP:
                    s["contradiction"] = 0.0
                for label in ("entailment", "contradiction"):
                    if best is None or s[label] > best[0]:
                        best = (s[label], label, span, unit)
        if best is None:
            return None
        score, label, span, unit = best
        if label == "entailment" and score >= ENTAIL:
            dropped = missing_qualifiers(indexer.find_hedges(unit),
                                         set(indexer.find_hedges(hypothesis)))
            verdict = "qualifier-dropped" if dropped else "supported"
            return _verdict(verdict, span, score, dropped)
        if label == "contradiction" and score >= CONTRADICT:
            return _verdict("contradicted", span, score)
        return None


def _verdict(verdict: str, span: Span, confidence: float, dropped: list[str] | None = None) -> dict:
    return {"verdict": verdict, "span_ids": [span.span_id], "dropped_qualifiers": dropped or [],
            "decided_by": "nli", "confidence": round(confidence, 2)}


_loaded: NLI | None = None


def load() -> NLI | None:
    """The model, loaded once per process; None if it can't load (the tier is then skipped)."""
    global _loaded
    if _loaded is None:
        try:
            _loaded = NLI(model_dir())
        except Exception:  # noqa: BLE001 - a broken install must not break verification
            return None
    return _loaded


def check(claim: str, spans: list[Span]) -> dict | None:
    nli = load() if available() else None
    return nli.check(claim, spans) if nli else None
