import os
import shutil

class FileOrganizer:
    def __init__(self, output_folder=None):
        self.output_folder = output_folder or os.path.expanduser("~/Downloads/OmniSort")

    def organize_file(self, file_path, metadata):
        if metadata.get("is_sensitive"):
            subfolder = "Sensitive"
        elif metadata.get("is_duplicate"):
            subfolder = "Duplicates"
        else:
            subfolder = metadata.get("category", "Other")

        dest_folder = os.path.join(self.output_folder, subfolder)
        os.makedirs(dest_folder, exist_ok=True)
        dest_path = self._unique_path(dest_folder, os.path.basename(file_path))
        shutil.move(file_path, dest_path)
        return dest_path

    def _unique_path(self, folder, filename):
        dest = os.path.join(folder, filename)
        if not os.path.exists(dest):
            return dest
        name, ext = os.path.splitext(filename)
        counter = 1
        while os.path.exists(dest):
            dest = os.path.join(folder, f"{name}_{counter}{ext}")
            counter += 1
        return dest
