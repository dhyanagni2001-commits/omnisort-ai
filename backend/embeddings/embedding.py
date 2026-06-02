import numpy as np

_model = None

def _get_model():
    global _model
    if _model is None:
        from fastembed import TextEmbedding
        _model = TextEmbedding("BAAI/bge-small-en-v1.5")
    return _model

def embed_text(text: str) -> list[float]:
    """
    Return a 384-dim embedding for text.
    Returns [] silently if fastembed is unavailable or the model fails to load.
    The pipeline degrades gracefully — files are still sorted, just not searchable.
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
    if not a or not b or len(a) != len(b):
        return 0.0
    va, vb = np.array(a), np.array(b)
    denom = float(np.linalg.norm(va) * np.linalg.norm(vb))
    return float(np.dot(va, vb) / denom) if denom > 0 else 0.0
