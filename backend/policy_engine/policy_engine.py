# Translates raw metadata signals into routing flags that FileOrganizer reads.

import json


class PolicyEngine:
    """Sets is_sensitive, sensitive_types, and is_duplicate flags on the metadata dict."""

    def apply_policies(self, file_path, metadata):
        """
        Reads sensitive_info (dict of {type: [matches]}) and duplicate flag,
        then writes three keys back into metadata in-place:
          - is_sensitive:   bool — True if any PII pattern matched
          - sensitive_types: JSON array of PII type names, e.g. '["email","ssn"]'
          - is_duplicate:   bool — True if the file's hash already exists in the DB
        """
        sensitive_info = metadata.get("sensitive_info", {})

        # Any non-empty sensitive_info dict means PII was found.
        metadata["is_sensitive"] = bool(sensitive_info)
        metadata["sensitive_types"] = json.dumps(list(sensitive_info.keys())) if sensitive_info else "[]"

        # 'duplicate' was set by DuplicateDetector.is_duplicate() earlier in the pipeline.
        metadata["is_duplicate"] = metadata.get("duplicate", False)
