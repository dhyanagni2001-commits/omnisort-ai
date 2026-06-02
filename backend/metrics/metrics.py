import time
import threading
from collections import deque

class Metrics:
    """Thread-safe in-process metrics store."""

    def __init__(self):
        self._lock = threading.Lock()

        # Sliding window of completion timestamps for files/min calculation
        self._processed_timestamps: deque[float] = deque()

        self.ocr_failures: int = 0
        self.llm_calls: int = 0
        self.duplicates: int = 0
        self.total_files: int = 0

        # Classification latency: running sum + count (NLP + LLM combined per file)
        self._classification_total_ms: float = 0.0
        self._classification_count: int = 0

        # LLM latency: running sum + count
        self._llm_total_ms: float = 0.0

    # ── record helpers ───────────────────────────────────────────────────────

    def record_file_processed(self, *, is_duplicate: bool = False):
        with self._lock:
            now = time.monotonic()
            self._processed_timestamps.append(now)
            self._trim_window(now)
            self.total_files += 1
            if is_duplicate:
                self.duplicates += 1

    def record_ocr_failure(self):
        with self._lock:
            self.ocr_failures += 1

    def record_classification(self, elapsed_ms: float):
        with self._lock:
            self._classification_total_ms += elapsed_ms
            self._classification_count += 1

    def record_llm_call(self, elapsed_ms: float):
        with self._lock:
            self.llm_calls += 1
            self._llm_total_ms += elapsed_ms

    # ── snapshot ─────────────────────────────────────────────────────────────

    def snapshot(self) -> dict:
        with self._lock:
            now = time.monotonic()
            self._trim_window(now)
            files_per_min = len(self._processed_timestamps)  # count in last 60 s

            avg_classification_ms = (
                self._classification_total_ms / self._classification_count
                if self._classification_count else 0.0
            )
            avg_llm_ms = (
                self._llm_total_ms / self.llm_calls
                if self.llm_calls else 0.0
            )
            duplicate_rate = (
                round(self.duplicates / self.total_files, 4)
                if self.total_files else 0.0
            )

            return {
                "files_per_min": files_per_min,
                "total_files": self.total_files,
                "ocr_failures": self.ocr_failures,
                "llm_calls": self.llm_calls,
                "avg_classification_ms": round(avg_classification_ms, 2),
                "avg_llm_ms": round(avg_llm_ms, 2),
                "duplicates": self.duplicates,
                "duplicate_rate": duplicate_rate,
            }

    def _trim_window(self, now: float):
        cutoff = now - 60.0
        while self._processed_timestamps and self._processed_timestamps[0] < cutoff:
            self._processed_timestamps.popleft()


# Module-level singleton shared across all imports
metrics = Metrics()
