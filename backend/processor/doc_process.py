# backend/processor/docx_processor.py
import docx

class DocxProcessor:
    def process(self, file_path):
        try:
            doc = docx.Document(file_path)
            text = "\n".join([paragraph.text for paragraph in doc.paragraphs])
            metadata = {
                "author": doc.core_properties.author,
                "created": doc.core_properties.created,
                "modified": doc.core_properties.modified
            }
            return text.strip(), metadata
        except Exception as e:
            raise ValueError(f"Error processing Word document {file_path}: {str(e)}")