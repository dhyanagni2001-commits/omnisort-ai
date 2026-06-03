# Semantic text embedding using fastembed (ONNX runtime, no PyTorch required).
# Model: BAAI/bge-small-en-v1.5 — 384-dim vectors, ~40 MB download on first use.
# Works on Python 3.13+. All failures return [] so file sorting is never interrupted.

import numpy as np

# Module-level cache so the model is loaded once per process.
_model = None


def _get_model():
    # Deferred import: the module can be imported even if fastembed isn't installed.
    global _model
    if _model is None:
        from fastembed import TextEmbedding
        _model = TextEmbedding("BAAI/bge-small-en-v1.5")
    return _model


def embed_text(text: str) -> list[float]:
    """
    Return a 384-dimensional embedding for the given text.
    Input is truncated to 1,000 characters — enough for classification signal.
    Returns an empty list on any failure; the caller stores NULL in the DB instead.
    """
    if not text or not text.strip():
        return []
    try:
        model = _get_model()
        result = list(model.embed([text[:1000]]))
        return result[0].tolist()
    except Exception:
        return []


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """
    Compute cosine similarity between two embedding vectors.
    Returns 0.0 if either vector is empty or the lengths don't match,
    and 0.0 if the denominator is zero (zero-magnitude vectors).
    """
    if not a or not b or len(a) != len(b):
        return 0.0
    va, vb = np.array(a), np.array(b)
    denom = float(np.linalg.norm(va) * np.linalg.norm(vb))
    return float(np.dot(va, vb) / denom) if denom > 0 else 0.0
