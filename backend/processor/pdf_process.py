# PDF text extraction using PyPDF2.
# For scanned PDFs (empty text layer), file_watcher falls back to OCRExtractor.

import PyPDF2


class PDFProcessor:
    """Extracts text and metadata from PDFs that have an embedded text layer."""

    def process(self, file_path):
        """
        Returns (text, metadata) where text is all pages concatenated and metadata
        is the PDF info dict (title, author, creator, etc.).
        Raises ValueError on any read error — caught by file_watcher's outer try/except.
        """
        try:
            with open(file_path, "rb") as file:
                reader = PyPDF2.PdfReader(file)
                # Concatenate text from every page.
                text = ""
                for page in reader.pages:
                    text += page.extract_text() or ""
                metadata = reader.metadata
            return text.strip(), metadata
        except Exception as e:
            raise ValueError(f"Error processing PDF {file_path}: {str(e)}")
