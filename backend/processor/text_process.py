# Plain text reader for .txt, .csv, and .md files.


class TextProcessor:
    """Reads a text file and returns its full contents as a string."""

    def process(self, file_path):
        """Opens the file in text mode, reads everything, and strips whitespace.
        Raises ValueError on read error."""
        try:
            with open(file_path, "r") as file:
                text = file.read()
            return text.strip()
        except Exception as e:
            raise ValueError(f"Error processing text file {file_path}: {str(e)}")
