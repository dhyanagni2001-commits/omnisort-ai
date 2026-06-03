# Stage 3.5 classifier — DistilBERT zero-shot NLI between keyword NLP and the LLM.
# Catches Medical / Financial / Academic documents that keywords miss, at zero API cost.
#
# Model: typeform/distilbert-base-uncased-mnli (~260 MB, downloads on first use)
# Requires: torch + transformers  (Python ≤ 3.12 / Docker python:3.11-slim)
# Degrades gracefully: returns None when unavailable so the LLM stage takes over.

_pipeline = None

# Human-readable descriptions fed as NLI candidate labels.
# The model scores each as an entailment hypothesis against the document text.
_CANDIDATE_LABELS = [
    "medical record or health document",
    "financial document bank statement or pay stub",
    "academic research paper thesis or lecture notes",
    "invoice bill receipt or purchase order",
    "resume curriculum vitae or job application",
    "legal contract agreement or terms of service",
    "general report memo letter or presentation",
]

# Maps each candidate label back to the category string used throughout the pipeline.
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
    # Lazy load so the import doesn't fail at startup when torch is unavailable.
    global _pipeline
    if _pipeline is None:
        from transformers import pipeline
        _pipeline = pipeline(
            "zero-shot-classification",
            model="typeform/distilbert-base-uncased-mnli",
            device=-1,  # -1 = CPU; set to 0 to use a GPU if available.
        )
    return _pipeline


class MLClassifier:
    """Zero-shot document classifier using DistilBERT fine-tuned on MultiNLI."""

    def classify(self, text: str, threshold: float = 0.50) -> str | None:
        """
        Returns the predicted category if the top NLI score exceeds `threshold`.
        Returns None when the model is unavailable or confidence is below the threshold,
        letting file_watcher fall through to the LLM stage.
        """
        snippet = text[:512].strip()
        if not snippet:
            return None

        try:
            pipe = _get_pipeline()
            result = pipe(snippet, _CANDIDATE_LABELS, multi_label=False)
            top_label: str  = result["labels"][0]
            top_score: float = result["scores"][0]

            # Below threshold means the model is uncertain — let the LLM decide instead.
            if top_score < threshold:
                return None

            return _LABEL_TO_CATEGORY.get(top_label)
        except Exception:
            # torch missing, model load failure, etc. — degrade silently.
            return None
