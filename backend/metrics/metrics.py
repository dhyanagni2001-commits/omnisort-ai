# Thread-safe in-process observability metrics.
# Uses a deque-based sliding 60-second window for the files/min throughput counter.
# Exposed as a module-level singleton so all imports share the same instance.

import time
import threading
from collections import deque


class Metrics:
    """Collects per-file and per-operation counters and latency accumulators."""

    def __init__(self):
        self._lock = threading.Lock()

        # Monotonic timestamps of recently completed files for the files/min window.
        self._processed_timestamps: deque[float] = deque()

        self.ocr_failures: int = 0
        self.llm_calls:    int = 0
        self.duplicates:   int = 0
        self.total_files:  int = 0

        # Running sum and count for average classification latency (NLP + optional LLM).
        self._classification_total_ms: float = 0.0
        self._classification_count:    int   = 0

        # Separate running sum for LLM-only round-trip latency.
        self._llm_total_ms: float = 0.0

    # ── record helpers ────────────────────────────────────────────────────────

    def record_file_processed(self, *, is_duplicate: bool = False):
        """Call once after every successfully sorted file."""
        with self._lock:
            now = time.monotonic()
            self._processed_timestamps.append(now)
            self._trim_window(now)
            self.total_files += 1
            if is_duplicate:
                self.duplicates += 1

    def record_ocr_failure(self):
        """Call when OCRExtractor raises an exception."""
        with self._lock:
            self.ocr_failures += 1

    def record_classification(self, elapsed_ms: float):
        """Call with the wall-clock time for the full classification block (NLP + LLM)."""
        with self._lock:
            self._classification_total_ms += elapsed_ms
            self._classification_count    += 1

    def record_llm_call(self, elapsed_ms: float):
        """Call with the OpenAI round-trip time. Separate from record_classification
        so avg_llm_ms reflects the API latency alone, not the entire classification block."""
        with self._lock:
            self.llm_calls     += 1
            self._llm_total_ms += elapsed_ms

    # ── snapshot ──────────────────────────────────────────────────────────────

    def snapshot(self) -> dict:
        """Return a point-in-time snapshot of all metrics. Exposed by GET /api/metrics."""
        with self._lock:
            now = time.monotonic()
            self._trim_window(now)

            # files_per_min = number of completions inside the rolling 60-second window.
            files_per_min = len(self._processed_timestamps)

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
                "files_per_min":         files_per_min,
                "total_files":           self.total_files,
                "ocr_failures":          self.ocr_failures,
                "llm_calls":             self.llm_calls,
                "avg_classification_ms": round(avg_classification_ms, 2),
                "avg_llm_ms":            round(avg_llm_ms, 2),
                "duplicates":            self.duplicates,
                "duplicate_rate":        duplicate_rate,
            }

    def _trim_window(self, now: float):
        # Remove timestamps older than 60 seconds from the left of the deque.
        # Must be called while holding self._lock.
        cutoff = now - 60.0
        while self._processed_timestamps and self._processed_timestamps[0] < cutoff:
            self._processed_timestamps.popleft()


# Module-level singleton — all imports get the same Metrics instance.
metrics = Metrics()
