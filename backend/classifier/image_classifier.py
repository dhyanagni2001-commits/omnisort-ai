import os
import re
from PIL import Image

SCREENSHOT_PATTERNS = [r"screenshot", r"screen.shot", r"screen_", r"capture", r"snip"]
SCREENSHOT_WIDTHS = {1280, 1366, 1440, 1920, 2560, 3840, 2732, 2388}
SCREENSHOT_HEIGHTS = {720, 768, 800, 900, 1024, 1080, 1440, 2160, 2048, 2732}

DOCUMENT_KEYWORDS = {
    "Invoices": ["invoice", "bill", "receipt", "total amount", "due date", "payment due"],
    "Resumes": ["resume", "curriculum vitae", " cv ", "objective", "work experience", "references"],
    "Legal": ["contract", "agreement", "terms and conditions", "hereby", "whereas", "shall"],
}

class ImageClassifier:
    def predict(self, image_path):
        filename = os.path.basename(image_path).lower()
        for pattern in SCREENSHOT_PATTERNS:
            if re.search(pattern, filename):
                return "Screenshots"
        try:
            w, h = Image.open(image_path).size
            if (w in SCREENSHOT_WIDTHS and h in SCREENSHOT_HEIGHTS) or \
               (h in SCREENSHOT_WIDTHS and w in SCREENSHOT_HEIGHTS):
                return "Screenshots"
        except Exception:
            pass
        return "Photos"

def classify_document(text):
    text_lower = text.lower()
    for category, keywords in DOCUMENT_KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            return category
    return "Documents"
