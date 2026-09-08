import json
from database.connection import DatabaseManager


class PipelineModel:
    @staticmethod
    def create(pipeline_id, name):
        DatabaseManager.execute_write(
            "INSERT INTO pipelines (id, name, status) VALUES (?, ?, ?)",
            (pipeline_id, name, "PENDING")
        )

    @staticmethod
    def update_status(pipeline_id, status):
        DatabaseManager.execute_write(
            "UPDATE pipelines SET status = ? WHERE id = ?", (status, pipeline_id)
        )

    @staticmethod
    def get_all():
        return DatabaseManager.execute_read("SELECT * FROM pipelines ORDER BY created_at DESC")

    @staticmethod
    def get_by_id(pipeline_id):
        rows = DatabaseManager.execute_read("SELECT * FROM pipelines WHERE id = ?", (pipeline_id,))
        return rows[0] if rows else None


class TaskModel:
    @staticmethod
    def create(task_id, pipeline_id, name, dependencies):
        deps_str = ",".join(dependencies) if dependencies else ""
        DatabaseManager.execute_write(
            "INSERT INTO tasks (id, pipeline_id, name, status, dependencies) VALUES (?, ?, ?, ?, ?)",
            (task_id, pipeline_id, name, "PENDING", deps_str)
        )

    @staticmethod
    def update_status(task_id, status, start=None, end=None):
        if start:
            DatabaseManager.execute_write(
                "UPDATE tasks SET status = ?, started_at = CURRENT_TIMESTAMP WHERE id = ?",
                (status, task_id)
            )
        elif end:
            DatabaseManager.execute_write(
                "UPDATE tasks SET status = ?, ended_at = CURRENT_TIMESTAMP WHERE id = ?",
                (status, task_id)
            )
        else:
            DatabaseManager.execute_write(
                "UPDATE tasks SET status = ? WHERE id = ?",
                (status, task_id)
            )

    @staticmethod
    def get_by_pipeline(pipeline_id):
        return DatabaseManager.execute_read("SELECT * FROM tasks WHERE pipeline_id = ?", (pipeline_id,))

    @staticmethod
    def get_by_id(task_id):
        rows = DatabaseManager.execute_read("SELECT * FROM tasks WHERE id = ?", (task_id,))
        return rows[0] if rows else None


class SystemMetricsModel:
    @staticmethod
    def record(cpu_utilization, memory_utilization):
        DatabaseManager.execute_write(
            "INSERT INTO system_metrics (cpu_utilization, memory_utilization) VALUES (?, ?)",
            (cpu_utilization, memory_utilization)
        )

    @staticmethod
    def get_recent(limit=30):
        return DatabaseManager.execute_read(
            "SELECT * FROM system_metrics ORDER BY timestamp DESC LIMIT ?",
            (limit,)
        )
