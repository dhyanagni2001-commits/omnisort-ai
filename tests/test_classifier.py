"""Unit tests for image classifier and document classifier."""
import os
import sys
import pytest
from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.classifier.image_classifier import ImageClassifier, classify_document

classifier = ImageClassifier()

# ─── ImageClassifier ────────────────────────────────────────────────────────

class TestImageClassifier:
    def _make_image(self, tmp_path, name, size=(800, 600)):
        img = Image.new("RGB", size, color=(100, 150, 200))
        path = str(tmp_path / name)
        img.save(path)
        return path

    def test_screenshot_by_filename(self, tmp_path):
        path = self._make_image(tmp_path, "Screenshot 2025-01-01.png")
        assert classifier.predict(path) == "Screenshots"

    def test_screenshot_filename_case_insensitive(self, tmp_path):
        path = self._make_image(tmp_path, "SCREENSHOT_001.jpg")
        assert classifier.predict(path) == "Screenshots"

    def test_screenshot_by_resolution_1080p(self, tmp_path):
        path = self._make_image(tmp_path, "capture.png", size=(1920, 1080))
        assert classifier.predict(path) == "Screenshots"

    def test_screenshot_by_resolution_4k(self, tmp_path):
        path = self._make_image(tmp_path, "image.png", size=(3840, 2160))
        assert classifier.predict(path) == "Screenshots"

    def test_photo_random_size(self, tmp_path):
        path = self._make_image(tmp_path, "photo.jpg", size=(800, 600))
        assert classifier.predict(path) == "Photos"

    def test_photo_portrait(self, tmp_path):
        path = self._make_image(tmp_path, "portrait.jpg", size=(600, 800))
        assert classifier.predict(path) == "Photos"

    def test_photo_square(self, tmp_path):
        path = self._make_image(tmp_path, "avatar.png", size=(512, 512))
        assert classifier.predict(path) == "Photos"


# ─── classify_document ──────────────────────────────────────────────────────

class TestDocumentClassifier:
    def test_invoice_keywords(self):
        assert classify_document("Invoice #1234\nTotal amount: $500\nDue date: Jan 1") == "Invoices"

    def test_receipt_keyword(self):
        assert classify_document("Receipt for payment of services rendered") == "Invoices"

    def test_resume_keyword(self):
        assert classify_document("Resume\nWork Experience\nEducation\nSkills\nReferences") == "Resumes"

    def test_cv_keyword(self):
        assert classify_document("Curriculum Vitae\nObjective: Senior Engineer role") == "Resumes"

    def test_contract_keyword(self):
        assert classify_document("This Agreement is hereby entered into by the parties") == "Legal"

    def test_terms_keyword(self):
        assert classify_document("Terms and conditions apply. Whereas the parties agree...") == "Legal"

    def test_generic_document(self):
        assert classify_document("This is a general report about quarterly earnings.") == "Documents"

    def test_empty_text(self):
        assert classify_document("") == "Documents"

    def test_whitespace_only(self):
        assert classify_document("   \n\n\t  ") == "Documents"
