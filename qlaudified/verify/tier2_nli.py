"""Optional NLI tier: DeBERTa-class MNLI on ONNX Runtime CPU, behind the [nli] extra. Sprint 3."""


def available() -> bool:
    try:
        import onnxruntime  # noqa: F401
    except ImportError:
        return False
    return True


def check(claim: str, spans) -> dict | None:
    raise NotImplementedError("Sprint 3: VER-3")
