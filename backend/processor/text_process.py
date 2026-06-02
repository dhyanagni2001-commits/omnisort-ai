# backend/processor/text_processor.py
class TextProcessor:
    def process(self, file_path):
        try:
            with open(file_path, "r") as file:
                text = file.read()
            return text.strip()
        except Exception as e:
            raise ValueError(f"Error processing text file {file_path}: {str(e)}")