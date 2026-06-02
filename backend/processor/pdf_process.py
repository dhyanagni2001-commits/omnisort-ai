# backend/processor/pdf_processor.py
import PyPDF2

class PDFProcessor:
    def process(self, file_path):
        try:
            with open(file_path, "rb") as file:
                reader = PyPDF2.PdfReader(file)
                text = ""
                for page in range(len(reader.pages)):
                    text += reader.pages[page].extract_text()
                metadata = reader.metadata
            return text.strip(), metadata
        except Exception as e:
            raise ValueError(f"Error processing PDF {file_path}: {str(e)}")