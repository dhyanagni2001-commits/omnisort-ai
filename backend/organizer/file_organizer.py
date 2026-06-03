# Moves files to their correct subfolder inside the output directory.
# Routing priority (read from metadata flags set by PolicyEngine):
#   Sensitive > Duplicates > category name

import os
import shutil


class FileOrganizer:
    """Handles the physical file move and collision-safe naming."""

    def __init__(self, output_folder=None):
        self.output_folder = output_folder or os.path.expanduser("~/Downloads/OmniSort")

    def organize_file(self, file_path, metadata):
        """
        Select the destination subfolder, create it if needed, generate a unique
        filename to avoid overwriting existing files, and move the file.
        Returns the absolute destination path.
        """
        # Sensitive always wins over Duplicates, which wins over the category.
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
        # If the target path is free, use it directly. Otherwise append _1, _2, … until free.
        dest = os.path.join(folder, filename)
        if not os.path.exists(dest):
            return dest
        name, ext = os.path.splitext(filename)
        counter = 1
        while os.path.exists(dest):
            dest = os.path.join(folder, f"{name}_{counter}{ext}")
            counter += 1
        return dest
