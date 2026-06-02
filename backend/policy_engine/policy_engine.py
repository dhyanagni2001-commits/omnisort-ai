import json

class PolicyEngine:
    def apply_policies(self, file_path, metadata):
        sensitive_info = metadata.get("sensitive_info", {})
        metadata["is_sensitive"] = bool(sensitive_info)
        metadata["sensitive_types"] = json.dumps(list(sensitive_info.keys())) if sensitive_info else "[]"
        metadata["is_duplicate"] = metadata.get("duplicate", False)
