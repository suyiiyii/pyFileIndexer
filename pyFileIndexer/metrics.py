from typing import Optional

PROM_AVAILABLE = False
try:
    from prometheus_client import Counter, Gauge, Histogram, Summary, start_http_server

    PROM_AVAILABLE = True
except Exception:
    pass


class _NoOp:
    def start_http_server(self, port: int, host: str = "0.0.0.0"):
        return

    def init(self, machine: str):
        return

    def enabled(self) -> bool:
        return False

    def set_scan_in_progress(self, value: int):
        return

    def set_queue_size(self, value: int):
        return

    def set_workers(self, value: int):
        return

    def inc_files(self, n: int = 1):
        return

    def inc_dirs(self, n: int = 1):
        return

    def inc_archives(self, archive_type: str, n: int = 1):
        return

    def inc_archive_entries(self, archive_type: str, n: int = 1):
        return

    def inc_errors(self, scope: str, n: int = 1):
        return

    def inc_db_writes(self, n: int = 1):
        return

    def inc_bytes(self, n: int):
        return

    def observe_file_duration(self, seconds: float):
        return

    def observe_db_flush(self, seconds: float, batch_size: int):
        return

    def set_scan_start_timestamp(self, ts: float):
        return

    def observe_scan_duration(self, seconds: float):
        return


class _Metrics:
    def __init__(self):
        self._machine: Optional[str] = None
        if not PROM_AVAILABLE:
            return
        self._files_scanned = Counter(
            "pyfileindexer_files_scanned_total",
            "Files processed",
            ["machine"],
        )
        self._dirs_scanned = Counter(
            "pyfileindexer_directories_scanned_total",
            "Directories processed",
            ["machine"],
        )
        self._archives_scanned = Counter(
            "pyfileindexer_archives_scanned_total",
            "Archives processed",
            ["machine", "type"],
        )
        self._archive_entries = Counter(
            "pyfileindexer_archive_entries_total",
            "Archive entries processed",
            ["machine", "type"],
        )
        self._errors_total = Counter(
            "pyfileindexer_errors_total",
            "Errors by scope",
            ["machine", "scope"],
        )
        self._db_writes_total = Counter(
            "pyfileindexer_db_writes_total",
            "Database writes (files)",
            ["machine"],
        )
        self._bytes_hashed_total = Counter(
            "pyfileindexer_bytes_hashed_total",
            "Bytes hashed",
            ["machine"],
        )
        self._scan_in_progress = Gauge(
            "pyfileindexer_scan_in_progress",
            "Scan in progress",
            ["machine"],
        )
        self._queue_files_pending = Gauge(
            "pyfileindexer_queue_files_pending",
            "File queue length",
            ["machine"],
        )
        self._workers_running = Gauge(
            "pyfileindexer_workers_running",
            "Active worker threads",
            ["machine"],
        )
        self._scan_file_duration = Histogram(
            "pyfileindexer_scan_file_duration_seconds",
            "Per-file processing duration",
            ["machine"],
        )
        self._db_flush_duration = Histogram(
            "pyfileindexer_db_flush_duration_seconds",
            "DB flush duration",
            ["machine"],
        )
        self._batch_size = Histogram(
            "pyfileindexer_batch_size",
            "Batch size",
            ["machine"],
        )
        self._scan_duration = Summary(
            "pyfileindexer_scan_duration_seconds",
            "Overall scan duration",
            ["machine"],
        )

    def start_http_server(self, port: int, host: str = "0.0.0.0"):
        if not PROM_AVAILABLE:
            return
        start_http_server(port, addr=host)

    def init(self, machine: str):
        self._machine = machine

    def enabled(self) -> bool:
        return True

    def _labels(self):
        return {"machine": self._machine or "unknown"}

    def set_scan_in_progress(self, value: int):
        if not PROM_AVAILABLE:
            return
        self._scan_in_progress.labels(**self._labels()).set(value)

    def set_queue_size(self, value: int):
        if not PROM_AVAILABLE:
            return
        self._queue_files_pending.labels(**self._labels()).set(value)

    def set_workers(self, value: int):
        if not PROM_AVAILABLE:
            return
        self._workers_running.labels(**self._labels()).set(value)

    def inc_files(self, n: int = 1):
        if not PROM_AVAILABLE:
            return
        self._files_scanned.labels(**self._labels()).inc(n)

    def inc_dirs(self, n: int = 1):
        if not PROM_AVAILABLE:
            return
        self._dirs_scanned.labels(**self._labels()).inc(n)

    def inc_archives(self, archive_type: str, n: int = 1):
        if not PROM_AVAILABLE:
            return
        labels = {**self._labels(), "type": archive_type}
        self._archives_scanned.labels(**labels).inc(n)

    def inc_archive_entries(self, archive_type: str, n: int = 1):
        if not PROM_AVAILABLE:
            return
        labels = {**self._labels(), "type": archive_type}
        self._archive_entries.labels(**labels).inc(n)

    def inc_errors(self, scope: str, n: int = 1):
        if not PROM_AVAILABLE:
            return
        labels = {**self._labels(), "scope": scope}
        self._errors_total.labels(**labels).inc(n)

    def inc_db_writes(self, n: int = 1):
        if not PROM_AVAILABLE:
            return
        self._db_writes_total.labels(**self._labels()).inc(n)

    def inc_bytes(self, n: int):
        if not PROM_AVAILABLE:
            return
        self._bytes_hashed_total.labels(**self._labels()).inc(n)

    def observe_file_duration(self, seconds: float):
        if not PROM_AVAILABLE:
            return
        self._scan_file_duration.labels(**self._labels()).observe(seconds)

    def observe_db_flush(self, seconds: float, batch_size: int):
        if not PROM_AVAILABLE:
            return
        self._db_flush_duration.labels(**self._labels()).observe(seconds)
        self._batch_size.labels(**self._labels()).observe(float(batch_size))

    def set_scan_start_timestamp(self, ts: float):
        return

    def observe_scan_duration(self, seconds: float):
        if not PROM_AVAILABLE:
            return
        self._scan_duration.labels(**self._labels()).observe(seconds)


metrics = _NoOp() if not PROM_AVAILABLE else _Metrics()
