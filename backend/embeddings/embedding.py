import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
from sentence_transformers import SentenceTransformer

class Embeddings:
    _model = None

    def __init__(self, model_name="sentence-transformers/all-MiniLM-L6-v2"):
        if Embeddings._model is None:
            Embeddings._model = SentenceTransformer(model_name)
        self.model = Embeddings._model

    def generate_text_embeddings(self, text):
        if not text or not text.strip():
            return np.zeros((1, 384))
        return self.model.encode([text], convert_to_numpy=True)

    def compute_similarity(self, e1, e2):
        return cosine_similarity(e1, e2)
