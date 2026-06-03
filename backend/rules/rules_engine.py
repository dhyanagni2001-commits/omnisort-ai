# User-defined keyword-to-folder routing loaded from custom_rules in settings.yaml.
# Runs after PII detection but before keyword NLP and the LLM — zero API cost, instant.
# A matching rule short-circuits the entire classification stack.

class RulesEngine:
    """Matches user-defined keyword rules against a file's name and content."""

    def __init__(self, rules: list):
        # Lowercase keywords at construction so every match is O(n) without case-folding.
        self._rules = [
            {
                "folder":   r["folder"],
                "keywords": [k.lower() for k in r.get("keywords", [])],
            }
            for r in (rules or [])
        ]

    def match(self, text: str, filename: str = "") -> str | None:
        """
        Return the folder name of the first rule whose keywords appear in either
        the filename or extracted text. Returns None if no rule matches.
        Rules are checked in the order they appear in settings.yaml — put the most
        specific rules first.
        """
        # Combine filename and text so keywords can match either source.
        haystack = (filename + " " + text).lower()
        for rule in self._rules:
            if any(kw in haystack for kw in rule["keywords"]):
                return rule["folder"]
        return None
