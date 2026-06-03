# On-device PII detector — pure regex, no model, no network call.
# Called twice per file: on the filename before the file is opened, and on the
# extracted text before any NLP or LLM stage. A single match routes the file to
# Sensitive/ and prevents all downstream API calls.

import re


class SensitiveDetector:
    """Detects emails, phone numbers, and SSNs using compiled regular expressions."""

    def __init__(self):
        # Compile once at construction; reused for every file in the process lifetime.
        self.patterns = {
            "email": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"),
            "phone": re.compile(r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b"),
            "ssn":   re.compile(r"\b\d{3}[-]?\d{2}[-]?\d{4}\b"),
        }

    def detect_sensitive_info(self, text):
        """
        Scan text for PII patterns. Returns a dict of {type: [matches]} for every
        pattern that finds at least one match, or an empty dict if no PII is found.
        An empty dict is falsy, which is how file_watcher checks the PII gate.
        """
        sensitive_info = {}
        for key, pattern in self.patterns.items():
            matches = pattern.findall(text)
            if matches:
                sensitive_info[key] = matches
        return sensitive_info
