"""
Zero-shot document classifier using DistilBERT fine-tuned on MultiNLI.
Model: typeform/distilbert-base-uncased-mnli (~260 MB, downloads on first use)

Requires: torch + transformers (Python ≤ 3.12 / Docker python:3.11-slim)
Degrades gracefully: returns None when unavailable so the LLM fallback takes over.
"""

_pipeline = None

# Natural-language descriptions fed as candidate labels to the NLI pipeline.
# The model scores each label as entailment/contradiction for the document text.
_CANDIDATE_LABELS = [
    "medical record or health document",
    "financial document bank statement or pay stub",
    "academic research paper thesis or lecture notes",
    "invoice bill receipt or purchase order",
    "resume curriculum vitae or job application",
    "legal contract agreement or terms of service",
    "general report memo letter or presentation",
]

_LABEL_TO_CATEGORY = {
    "medical record or health document":               "Medical",
    "financial document bank statement or pay stub":   "Financial",
    "academic research paper thesis or lecture notes": "Academic",
    "invoice bill receipt or purchase order":          "Invoices",
    "resume curriculum vitae or job application":      "Resumes",
    "legal contract agreement or terms of service":    "Legal",
    "general report memo letter or presentation":      "Documents",
}


def _get_pipeline():
    global _pipeline
    if _pipeline is None:
        from transformers import pipeline
        _pipeline = pipeline(
            "zero-shot-classification",
            model="typeform/distilbert-base-uncased-mnli",
            device=-1,  # CPU; set to 0 for GPU
        )
    return _pipeline


class MLClassifier:
    """
    Stage 3.5 in the classification pipeline.
    Sits between keyword NLP (classify_document) and the OpenAI LLM fallback.
    Called only when NLP returned 'Documents' and no PII was found.
    """

    def classify(self, text: str, threshold: float = 0.50) -> str | None:
        """
        Zero-shot classify text using DistilBERT NLI.

        Returns the predicted category string if the top label scores above
        `threshold`, or None if the model is unavailable or confidence is low.
        Returning None lets file_watcher fall through to the LLM stage.
        """
        snippet = text[:512].strip()
        if not snippet:
            return None
        try:
            pipe = _get_pipeline()
            result = pipe(snippet, _CANDIDATE_LABELS, multi_label=False)
            top_label: str = result["labels"][0]
            top_score: float = result["scores"][0]
            if top_score < threshold:
                return None
            return _LABEL_TO_CATEGORY.get(top_label)
        except Exception:
            return None
