import shutil
import pytesseract
from PIL import Image

TESSERACT_CANDIDATES = [
    "/usr/local/bin/tesseract",
    "/opt/homebrew/bin/tesseract",
    "/usr/bin/tesseract",
]

def _find_tesseract(config_path=None):
    if config_path and shutil.which(config_path):
        return config_path
    for path in TESSERACT_CANDIDATES:
        if shutil.which(path):
            return path
    found = shutil.which("tesseract")
    return found or TESSERACT_CANDIDATES[0]

class OCRExtractor:
    def __init__(self, tesseract_path=None):
        pytesseract.pytesseract.tesseract_cmd = _find_tesseract(tesseract_path)

    def extract_text(self, image_path):
        image = Image.open(image_path)
        return pytesseract.image_to_string(image).strip()

    def extract_text_from_image(self, image):
        return pytesseract.image_to_string(image).strip()

    def extract_text_from_pdf_page(self, pdf_path: str, page_index: int = 0) -> str:
        """OCR fallback for scanned PDFs that have no text layer."""
        try:
            import fitz
            doc = fitz.open(pdf_path)
            if not doc or len(doc) == 0:
                return ""
            pix = doc[page_index].get_pixmap(dpi=150)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            return self.extract_text_from_image(img)
        except Exception:
            return ""
