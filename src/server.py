import time
import threading
import signal
import sys
from pathlib import Path
from config.settings import Config
from database.connection import DatabaseManager
from database.models import PipelineModel, TaskModel
from src.drms import DRMSManager
from src.scheduler import DAGScheduler
from src.utils.logger import get_logger

logger = get_logger("Orchestrator")


class OrchestratorServer:
    """
    Central Hub / Orchestrator.
    Continuously monitors active pipelines, requests runnable tasks from the DAG Scheduler,
    checks admission control via DRMS, and manages concurrent worker execution.
    """

    def __init__(self, poll_interval: float = 2.0):
        self.poll_interval = poll_interval
        self._stop_event = threading.Event()
        self._running_tasks = set()
        self._lock = threading.Lock()
        self._thread = None

        # Ensure logs directory exists for task stdout/stderr
        self.logs_dir = Path(getattr(Config, "LOG_DIR", "logs"))
        self.logs_dir.mkdir(parents=True, exist_ok=True)

    def start(self, blocking: bool = False):
        """Starts the orchestrator engine loop."""
        logger.info("Initializing EDA Orchestrator Server...")
        DatabaseManager.init_db()

        self._stop_event.clear()
        if blocking:
            self._run_loop()
        else:
            self._thread = threading.Thread(target=self._run_loop, daemon=True, name="Orchestrator-Hub")
            self._thread.start()
            logger.info("Orchestrator Server running in background thread.")

    def stop(self):
        """Signals graceful shutdown."""
        logger.info("Stopping Orchestrator Server...")
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)
        logger.info("Orchestrator Server stopped.")

    def _run_loop(self):
        """Main coordination loop."""
        logger.info("Orchestrator heartbeat loop started.")
        while not self._stop_event.is_set():
            try:
                # 1. Periodically record system health to database
                DRMSManager.record_metrics_to_db()

                # 2. Query active pipelines
                all_pipelines = PipelineModel.get_all()
                active_pipelines = [
                    p for p in all_pipelines
                    if p["status"] in ("PENDING", "RUNNING")
                ]

                # 3. Schedule ready tasks for each active pipeline
                for pipeline in active_pipelines:
                    pipe_id = pipeline["id"]

                    # Transition PENDING -> RUNNING
                    if pipeline["status"] == "PENDING":
                        PipelineModel.update_status(pipe_id, "RUNNING")
                        logger.info(f"Pipeline '{pipe_id}' ({pipeline['name']}) transitioned to RUNNING.")

                    # Fetch ready tasks from DAGScheduler
                    ready_tasks = DAGScheduler.get_ready_tasks(pipe_id)

                    for task in ready_tasks:
                        task_id = task["id"]

                        with self._lock:
                            if task_id in self._running_tasks:
                                continue

                        # Check DRMS admission capacity
                        if not DRMSManager.can_dispatch():
                            logger.debug("DRMS capacity threshold reached or slots full. Deferring dispatch.")
                            break

                        # Acquire slot & dispatch
                        if DRMSManager.acquire_slot():
                            with self._lock:
                                self._running_tasks.add(task_id)

                            # Launch worker thread
                            worker = threading.Thread(
                                target=self._execute_task_worker,
                                args=(task, pipe_id),
                                daemon=True,
                                name=f"Worker-{task_id}"
                            )
                            worker.start()

                    # Check if pipeline has reached completion
                    DAGScheduler.check_pipeline_completion(pipe_id)

            except Exception as e:
                logger.error(f"Error in orchestrator coordination loop: {e}", exc_info=True)

            self._stop_event.wait(self.poll_interval)

    def _execute_task_worker(self, task: dict, pipeline_id: str):
        """
        Worker thread that executes an individual EDA stage.
        Streams stdout/stderr to task log file and updates status upon completion/failure.
        """
        task_id = task["id"]
        task_name = task["name"]
        log_file_path = self.logs_dir / f"{pipeline_id}_{task_id}.log"

        logger.info(f"Starting task '{task_name}' [{task_id}] for pipeline '{pipeline_id}'...")
        TaskModel.update_status(task_id, "RUNNING", start=True)

        success = True
        try:
            with open(log_file_path, "w", encoding="utf-8") as log_f:
                log_f.write(f"=== EDA Task Execution: {task_name} ({task_id}) ===\n")
                log_f.write(f"Pipeline: {pipeline_id}\n")
                log_f.write(f"Started at: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")

                # Simulated EDA stage execution
                log_f.write(f"[INFO] Initializing EDA tool environment for {task_name}...\n")
                log_f.flush()
                time.sleep(2.0)  # Simulated processing time

                log_f.write(f"[INFO] Processing stage inputs and geometry...\n")
                log_f.write(f"[INFO] Running design rule and timing checks...\n")
                log_f.flush()
                time.sleep(1.5)

                log_f.write(f"[INFO] Stage {task_name} completed with 0 errors.\n")
                log_f.write(f"Ended at: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")

        except Exception as e:
            logger.error(f"Task '{task_id}' encountered error: {e}")
            success = False

        finally:
            # Update task state in database
            if success:
                TaskModel.update_status(task_id, "COMPLETED", end=True)
                logger.info(f"Task '{task_name}' [{task_id}] COMPLETED successfully.")
            else:
                TaskModel.update_status(task_id, "FAILED", end=True)
                logger.error(f"Task '{task_name}' [{task_id}] FAILED. Cascading failure.")
                DAGScheduler.handle_failed_task(pipeline_id, task_id)

            # Release DRMS slot and cleanup internal set
            DRMSManager.release_slot()
            with self._lock:
                self._running_tasks.discard(task_id)

            # Check if this completed the entire pipeline
            is_done, final_status = DAGScheduler.check_pipeline_completion(pipeline_id)
            if is_done:
                logger.info(f"Pipeline '{pipeline_id}' FINISHED with status: {final_status}")


class JobOrchestrator(OrchestratorServer):
    """
    Job Orchestrator providing static dispatch_new_pipeline() method
    matching user specification.
    """
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = OrchestratorServer(poll_interval=2.0)
            cls._instance.start(blocking=False)
        return cls._instance

    @classmethod
    def dispatch_new_pipeline(cls, pipeline_id: str, pipeline_name: str, tasks: list):
        """Dispatches a new pipeline into SQLite and ensures orchestrator loop is active."""
        DatabaseManager.init_db()
        PipelineModel.create(pipeline_id, pipeline_name)
        for task in tasks:
            deps = task.get("dependencies", [])
            TaskModel.create(task["id"], pipeline_id, task["name"], deps)

        logger.info(f"Dispatched new pipeline '{pipeline_id}' ({pipeline_name}) with {len(tasks)} tasks.")
        cls.get_instance()


def main():
    """CLI entrypoint for eda-server command."""
    server = OrchestratorServer(poll_interval=2.0)

    def _signal_handler(sig, frame):
        print("\nShutdown signal received. Terminating orchestrator...")
        server.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    print("=" * 60)
    print("  EDA FLOW AUTOMATION - ORCHESTRATOR HUB")
    print("=" * 60)
    server.start(blocking=True)


if __name__ == "__main__":
    main()