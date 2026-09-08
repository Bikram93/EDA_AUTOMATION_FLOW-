from flask import Flask, render_template, request, jsonify, redirect, url_for
import uuid
import os
from pathlib import Path
from config.settings import Config
from database.connection import DatabaseManager
from database.models import PipelineModel, TaskModel, SystemMetricsModel
from src.server import JobOrchestrator, OrchestratorServer
from src.drms import DRMSMonitor, DRMSManager
from src.scheduler import DAGScheduler
from src.utils.logger import get_logger

logger = get_logger("WebGUI")

# Initialize Flask application
app = Flask(
    __name__,
    template_folder=str(Path(__file__).resolve().parent / "templates"),
    static_folder=str(Path(__file__).resolve().parent / "static")
)
app.config.from_object(Config)

# Initialize database and background telemetry system
DatabaseManager.init_db()
drms = DRMSMonitor(interval=getattr(Config, "SYSTEM_MONITOR_INTERVAL_SECS", 5))
drms.start()

# Initialize background job orchestrator
orchestrator = JobOrchestrator.get_instance()


# ----------------------------------------------------------------------------
# Web UI Routes
# ----------------------------------------------------------------------------

@app.route("/")
def index():
    """Renders main dashboard overview with pipelines & system telemetry."""
    pipelines = PipelineModel.get_all()
    health = DRMSManager.get_system_health()
    metrics = DatabaseManager.execute_read(
        "SELECT * FROM system_metrics ORDER BY timestamp DESC LIMIT 1"
    )
    current_metrics = dict(metrics[0]) if metrics else {"cpu_utilization": 0, "memory_utilization": 0}

    return render_template(
        "dashboard.html",
        pipelines=pipelines,
        health=health,
        metrics=current_metrics
    )


# URL rule alias for template compatibility
app.add_url_rule('/', endpoint='dashboard', view_func=index)


@app.route("/pipeline/submit", methods=["POST"])
@app.route("/api/pipeline/create", methods=["POST"])
def submit_pipeline():
    """
    Submits a new standard production EDA flow run:
    Synthesis -> Floorplan -> Place & Route -> (Parallel: DRC and LVS).
    """
    pipeline_name = request.form.get("name") if request.form else None
    if not pipeline_name and request.is_json:
        pipeline_name = request.json.get("name")
    if not pipeline_name:
        pipeline_name = "EDA_Flow_Run"

    pipeline_id = f"pipe_{uuid.uuid4().hex[:8]}"

    # Production Standard Design Validation Flow Definition (with Parallel DRC & LVS)
    tasks = [
        {"id": f"syn_{pipeline_id}", "name": "RTL Synthesis", "dependencies": []},
        {"id": f"floorplan_{pipeline_id}", "name": "Floorplanning", "dependencies": [f"syn_{pipeline_id}"]},
        {"id": f"pnr_{pipeline_id}", "name": "Place & Route", "dependencies": [f"floorplan_{pipeline_id}"]},
        {"id": f"drc_{pipeline_id}", "name": "Design Rule Check (DRC)", "dependencies": [f"pnr_{pipeline_id}"]},
        {"id": f"lvs_{pipeline_id}", "name": "Layout Vs Schematic (LVS)", "dependencies": [f"pnr_{pipeline_id}"]}
    ]

    JobOrchestrator.dispatch_new_pipeline(pipeline_id, pipeline_name, tasks)

    if request.is_json:
        return jsonify({
            "status": "success",
            "pipeline_id": pipeline_id,
            "pipeline_name": pipeline_name,
            "task_count": len(tasks)
        }), 201

    return redirect(url_for("index"))


@app.route("/pipeline/<pipeline_id>")
def pipeline_details(pipeline_id):
    """Renders pipeline view with interactive Cytoscape DAG and task table."""
    pipeline = PipelineModel.get_by_id(pipeline_id)
    if not pipeline:
        return "Pipeline not found", 404

    tasks = TaskModel.get_by_pipeline(pipeline_id)
    health = DRMSManager.get_system_health()

    return render_template(
        "dashboard.html",
        active_pipeline=pipeline,
        tasks=tasks,
        health=health,
        pipelines=PipelineModel.get_all()
    )


# URL rule alias for template compatibility
app.add_url_rule('/pipeline/<pipeline_id>', endpoint='pipeline_detail', view_func=pipeline_details)


@app.route("/job/<task_id>")
def job_detail(task_id):
    """Renders execution log inspection and stage detail for a specific task."""
    task = TaskModel.get_by_id(task_id)
    if not task:
        return "Task not found", 404

    pipeline = PipelineModel.get_by_id(task["pipeline_id"])
    log_file = Path(getattr(Config, "LOG_DIR", "logs")) / f"{task['pipeline_id']}_{task_id}.log"
    log_content = "Log file not yet generated or stage is still waiting to execute."

    if log_file.exists():
        try:
            with open(log_file, "r", encoding="utf-8") as f:
                log_content = f.read()
        except Exception as e:
            log_content = f"Error reading log file: {e}"

    return render_template(
        "job_detail.html",
        task=task,
        pipeline=pipeline,
        log_content=log_content
    )


# ----------------------------------------------------------------------------
# REST API Endpoints
# ----------------------------------------------------------------------------

@app.route("/api/pipeline/<pipeline_id>/graph")
@app.route("/api/pipeline/<pipeline_id>/dag")
def pipeline_graph_json(pipeline_id):
    """
    Returns Cytoscape.js formatted elements array:
    Nodes: [{"data": {"id": "...", "label": "...", "status": "..."}}]
    Edges: [{"data": {"source": "...", "target": "..."}}]
    """
    tasks = TaskModel.get_by_pipeline(pipeline_id)
    elements = []

    for task in tasks:
        elements.append({
            "data": {
                "id": task["id"],
                "name": task["name"],
                "label": f"{task['name']} ({task['status']})",
                "status": task["status"]
            }
        })
        if task["dependencies"]:
            for dep in task["dependencies"].split(","):
                dep_clean = dep.strip()
                if dep_clean:
                    elements.append({
                        "data": {
                            "id": f"{dep_clean}->{task['id']}",
                            "source": dep_clean,
                            "target": task["id"]
                        }
                    })

    return jsonify(elements)


@app.route("/api/health")
def api_health():
    """Returns real-time host telemetry (CPU, RAM, slots)."""
    return jsonify(DRMSManager.get_system_health())


@app.route("/api/pipeline/<pipeline_id>/status")
def api_pipeline_status(pipeline_id):
    """Returns pipeline status and task status map for live frontend polling."""
    pipe = PipelineModel.get_by_id(pipeline_id)
    if not pipe:
        return jsonify({"error": "Pipeline not found"}), 404

    tasks = TaskModel.get_by_pipeline(pipeline_id)
    return jsonify({
        "pipeline": dict(pipe),
        "tasks": [dict(t) for t in tasks]
    })


@app.route("/api/job/<task_id>/logs")
def api_job_logs(task_id):
    """Returns raw execution log text for real-time log polling."""
    task = TaskModel.get_by_id(task_id)
    if not task:
        return jsonify({"error": "Task not found"}), 404

    log_file = Path(getattr(Config, "LOG_DIR", "logs")) / f"{task['pipeline_id']}_{task_id}.log"
    if not log_file.exists():
        return jsonify({"logs": "Waiting for stage execution to start..."})

    try:
        with open(log_file, "r", encoding="utf-8") as f:
            return jsonify({"logs": f.read()})
    except Exception as e:
        return jsonify({"logs": f"Error reading log: {e}"})


def main():
    """CLI entrypoint for eda-web command."""
    host = getattr(Config, "HOST", "0.0.0.0")
    port = getattr(Config, "PORT", 5000)

    print("=" * 60)
    print("  EDA FLOW AUTOMATION - WEB GUI & REST API")
    print(f"  Serving dashboard at: http://127.0.0.1:{port}")
    print("=" * 60)
    app.run(host=host, port=port, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()