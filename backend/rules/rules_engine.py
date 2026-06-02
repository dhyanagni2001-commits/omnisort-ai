class RulesEngine:
    """
    Matches user-defined keyword rules against filename + content.
    Runs before NLP/LLM — zero API cost, instant.

    Config shape (settings.yaml):
        custom_rules:
          - folder: Bank
            keywords: ["bank statement", "account number", "HDFC"]
          - folder: Tax
            keywords: ["form 16", "income tax", "assessment year"]
    """

    def __init__(self, rules: list):
        self._rules = [
            {
                "folder": r["folder"],
                "keywords": [k.lower() for k in r.get("keywords", [])],
            }
            for r in (rules or [])
        ]

    def match(self, text: str, filename: str = "") -> str | None:
        """Return the first matching folder name, or None if no rule matches."""
        haystack = (filename + " " + text).lower()
        for rule in self._rules:
            if any(kw in haystack for kw in rule["keywords"]):
                return rule["folder"]
        return None
