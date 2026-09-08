import psutil
import threading
from config.settings import Config
from database.models import SystemMetricsModel
from src.utils.logger import get_logger

logger = get_logger("DRMS")


class DRMSManager:
    """
    Distributed Resource Management System (DRMS).
    Monitors hardware health (CPU & Memory) and enforces execution slot concurrency limits.
    """
    _lock = threading.Lock()
    _active_jobs = 0

    @classmethod
    def get_system_health(cls) -> dict:
        """Inspects current host CPU, RAM, and active worker slots."""
        cpu = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory().percent

        with cls._lock:
            active = cls._active_jobs

        max_jobs = getattr(Config, "MAX_CONCURRENT_JOBS", 4)
        available = max(0, max_jobs - active)

        return {
            "cpu_utilization": round(cpu, 1),
            "memory_utilization": round(mem, 1),
            "active_jobs": active,
            "max_jobs": max_jobs,
            "available_slots": available
        }

    @classmethod
    def can_dispatch(cls) -> bool:
        """
        Determines whether the system has capacity to start a new job.
        Ensures available slots exist and host CPU/RAM are below safety thresholds.
        """
        health = cls.get_system_health()
        max_cpu = getattr(Config, "MAX_CPU_PERCENT", 85.0)
        max_mem = getattr(Config, "MAX_MEMORY_PERCENT", 95.0)

        has_slot = health["available_slots"] > 0
        cpu_ok = health["cpu_utilization"] < max_cpu
        mem_ok = health["memory_utilization"] < max_mem

        return has_slot and cpu_ok and mem_ok

    @classmethod
    def acquire_slot(cls) -> bool:
        """
        Thread-safely claims an execution slot for an incoming task.
        Returns True if acquired, False if slot limit reached.
        """
        with cls._lock:
            max_jobs = getattr(Config, "MAX_CONCURRENT_JOBS", 4)
            if cls._active_jobs < max_jobs:
                cls._active_jobs += 1
                logger.info(f"Slot acquired. Active jobs: {cls._active_jobs}/{max_jobs}")
                return True
            logger.warning(f"Slot acquisition denied. Active jobs: {cls._active_jobs}/{max_jobs}")
            return False

    @classmethod
    def release_slot(cls):
        """Thread-safely frees a slot when a task terminates."""
        with cls._lock:
            max_jobs = getattr(Config, "MAX_CONCURRENT_JOBS", 4)
            if cls._active_jobs > 0:
                cls._active_jobs -= 1
                logger.info(f"Slot released. Active jobs: {cls._active_jobs}/{max_jobs}")

    @classmethod
    def record_metrics_to_db(cls):
        """Records instantaneous CPU and Memory utilization to the database."""
        try:
            cpu = psutil.cpu_percent(interval=None)
            mem = psutil.virtual_memory().percent
            SystemMetricsModel.record(round(cpu, 1), round(mem, 1))
        except Exception as e:
            logger.error(f"Failed to record system metrics into database: {e}")


class DRMSMonitor:
    """Telemetry monitor daemon wrapper matching user specification."""

    def __init__(self, interval: int = 5):
        self.interval = interval
        self._thread = None
        self._stop_event = threading.Event()

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()

        def _run():
            logger.info("DRMSMonitor telemetry daemon started.")
            # Warm up cpu
            psutil.cpu_percent(interval=0.1)
            while not self._stop_event.is_set():
                DRMSManager.record_metrics_to_db()
                self._stop_event.wait(self.interval)

        self._thread = threading.Thread(target=_run, daemon=True, name="DRMS-Telemetry")
        self._thread.start()

    def stop(self):
        if self._thread:
            self._stop_event.set()
            self._thread.join(timeout=2.0)
            logger.info("DRMSMonitor telemetry daemon stopped.")