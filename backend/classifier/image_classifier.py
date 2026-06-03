# Stage 1 & 3 classifiers — images use PIL heuristics; documents use keyword NLP.

import os
import re
from PIL import Image

# Filename substrings that reliably indicate a screenshot.
SCREENSHOT_PATTERNS = [r"screenshot", r"screen.shot", r"screen_", r"capture", r"snip"]

# Common screen widths and heights. If both dimensions match known screen sizes,
# the image is classified as a screenshot regardless of filename.
SCREENSHOT_WIDTHS  = {1280, 1366, 1440, 1920, 2560, 3840, 2732, 2388}
SCREENSHOT_HEIGHTS = {720, 768, 800, 900, 1024, 1080, 1440, 2160, 2048, 2732}

# Keyword lists for the three document categories detectable without an LLM.
DOCUMENT_KEYWORDS = {
    "Invoices": ["invoice", "bill", "receipt", "total amount", "due date", "payment due"],
    "Resumes":  ["resume", "curriculum vitae", " cv ", "objective", "work experience", "references"],
    "Legal":    ["contract", "agreement", "terms and conditions", "hereby", "whereas", "shall"],
}


class ImageClassifier:
    """Classifies image files as Screenshots or Photos using filename and pixel dimensions."""

    def predict(self, image_path):
        # Check filename first — cheapest path.
        filename = os.path.basename(image_path).lower()
        for pattern in SCREENSHOT_PATTERNS:
            if re.search(pattern, filename):
                return "Screenshots"

        # Open the image and check if its dimensions match a known screen resolution.
        try:
            w, h = Image.open(image_path).size
            if (w in SCREENSHOT_WIDTHS and h in SCREENSHOT_HEIGHTS) or \
               (h in SCREENSHOT_WIDTHS and w in SCREENSHOT_HEIGHTS):
                return "Screenshots"
        except Exception:
            # Corrupt or unreadable images fall through to Photos.
            pass

        return "Photos"


def classify_document(text):
    """Stage-3 keyword NLP: returns a category or 'Documents' if nothing matches."""
    text_lower = text.lower()
    for category, keywords in DOCUMENT_KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            return category
    # 'Documents' is the signal for the next stage (DistilBERT / LLM) to take over.
    return "Documents"
