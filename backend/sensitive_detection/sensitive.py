
import re

class SensitiveDetector:
    def __init__(self):
        self.patterns = {
            "email": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"),
            "phone": re.compile(r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b"),
            "ssn": re.compile(r"\b\d{3}[-]?\d{2}[-]?\d{4}\b")
        }

    def detect_sensitive_info(self, text):
        sensitive_info = {}
        for key, pattern in self.patterns.items():
            matches = pattern.findall(text)
            if matches:
                sensitive_info[key] = matches
        return sensitive_info