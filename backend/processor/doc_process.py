# DOCX text extraction using python-docx.

import docx


class DocxProcessor:
    """Extracts plain text and core properties from .docx / .doc files."""

    def process(self, file_path):
        """
        Returns (text, metadata) where text is all paragraphs joined by newlines
        and metadata contains author, created, and modified timestamps.
        Raises ValueError on error.
        """
        try:
            doc = docx.Document(file_path)
            # Join all paragraphs; empty paragraphs become blank lines.
            text = "\n".join(paragraph.text for paragraph in doc.paragraphs)
            metadata = {
                "author":   doc.core_properties.author,
                "created":  doc.core_properties.created,
                "modified": doc.core_properties.modified,
            }
            return text.strip(), metadata
        except Exception as e:
            raise ValueError(f"Error processing Word document {file_path}: {str(e)}")
