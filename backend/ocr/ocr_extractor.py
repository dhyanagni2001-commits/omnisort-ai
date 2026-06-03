# OCR text extraction — wraps pytesseract for image files and scanned PDFs.

import shutil
import pytesseract
from PIL import Image

# Common Tesseract install locations across macOS (Intel and Apple Silicon) and Linux.
TESSERACT_CANDIDATES = [
    "/usr/local/bin/tesseract",   # macOS Intel / Homebrew
    "/opt/homebrew/bin/tesseract", # macOS Apple Silicon
    "/usr/bin/tesseract",          # Linux
]


def _find_tesseract(config_path=None):
    # Try the configured path first, then the known candidates, then PATH lookup.
    if config_path and shutil.which(config_path):
        return config_path
    for path in TESSERACT_CANDIDATES:
        if shutil.which(path):
            return path
    found = shutil.which("tesseract")
    return found or TESSERACT_CANDIDATES[0]


class OCRExtractor:
    """Runs Tesseract OCR on images and scanned PDFs."""

    def __init__(self, tesseract_path=None):
        # Set the binary path once so pytesseract doesn't search on every call.
        pytesseract.pytesseract.tesseract_cmd = _find_tesseract(tesseract_path)

    def extract_text(self, image_path):
        """OCR a file on disk. Used for .jpg, .png, .webp, etc."""
        image = Image.open(image_path)
        return pytesseract.image_to_string(image).strip()

    def extract_text_from_image(self, image):
        """OCR an in-memory PIL Image. Used by extract_text_from_pdf_page."""
        return pytesseract.image_to_string(image).strip()

    def extract_text_from_pdf_page(self, pdf_path: str, page_index: int = 0) -> str:
        """
        OCR fallback for scanned PDFs that have no embedded text layer.
        PyMuPDF renders the page to a pixmap at 150 DPI, which is then passed to
        Tesseract. Higher DPI improves accuracy but increases render time.
        Returns '' on any error so the pipeline continues without crashing.
        """
        try:
            import fitz  # PyMuPDF
            doc = fitz.open(pdf_path)
            if not doc or len(doc) == 0:
                return ""
            pix = doc[page_index].get_pixmap(dpi=150)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            return self.extract_text_from_image(img)
        except Exception:
            return ""
