# Stage 4 (last resort) classifier — calls GPT-4o-mini only when all local stages
# returned "Documents" and no PII was found. Never called for sensitive files.

import os
from openai import OpenAI

# All valid outputs. Anything else from the model is treated as "Documents".
CATEGORIES = [
    "Invoices",
    "Resumes",
    "Legal",
    "Medical",
    "Financial",
    "Academic",
    "Documents",
    "Other",
]

# System prompt constrains the model to a single category word with no explanation.
_SYSTEM_PROMPT = (
    "You are a file classification assistant. "
    "Given the extracted text from a document, classify it into exactly one of these categories:\n"
    + "\n".join(f"- {c}" for c in CATEGORIES)
    + "\n\n"
    "Rules:\n"
    "- Invoices: bills, receipts, purchase orders, payment requests.\n"
    "- Resumes: CVs, job applications, career summaries.\n"
    "- Legal: contracts, agreements, terms of service, legal notices.\n"
    "- Medical: lab reports, prescriptions, medical records, health documents.\n"
    "- Financial: bank statements, tax forms, investment reports, pay stubs.\n"
    "- Academic: research papers, syllabi, transcripts, lecture notes, assignments.\n"
    "- Documents: general reports, memos, presentations, letters.\n"
    "- Other: anything that does not clearly fit the above.\n\n"
    "Respond with ONLY the category name — no explanation, no punctuation."
)


class LLMClassifier:
    """Calls GPT-4o-mini to classify ambiguous documents that keyword NLP and DistilBERT missed."""

    def __init__(self):
        # API key is read from the environment so it is never hardcoded.
        self._client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

    def classify(self, text: str) -> str:
        # Trim to 2,000 chars — enough context for classification, cheap on tokens.
        snippet = text[:2000].strip()
        if not snippet:
            return "Documents"

        try:
            response = self._client.chat.completions.create(
                model="gpt-4o-mini",
                max_tokens=16,  # One word is all we need.
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user",   "content": f"Document text:\n\n{snippet}"},
                ],
            )
            result = response.choices[0].message.content.strip()
            # Reject any response that isn't in the known list.
            return result if result in CATEGORIES else "Documents"
        except Exception:
            # Network errors, quota exhaustion, etc. all fall back to "Documents".
            return "Documents"
