import os
import uuid
from pathlib import Path
from flask import Flask, render_template, request, jsonify, redirect, url_for
from config.settings import Config
from database.connection import DatabaseManager
from database.models import PipelineModel, TaskModel, SystemMetricsModel
from src.drms import DRMSManager
from src.scheduler import DAGScheduler
from src.server import OrchestratorServer
from src.utils.logger import get_logger

logger = get_logger("WebGUI")

# Initialize Flask application
app = Flask(
    __name__,
    template_folder=str(Path(__file__).resolve().parent / "templates"),
    static_folder=str(Path(__file__).resolve().parent / "static")
)
app.config["SECRET_KEY"] = getattr(Config, "SECRET_KEY", "eda-secret-key-default")

# Orchestrator background instance
orchestrator = None


# ----------------------------------------------------------------------------
# HTML UI Routes
# ----------------------------------------------------------------------------

@app.route("/")
def dashboard():
    """Renders the main dashboard overview with pipelines & system health."""
    pipelines = PipelineModel.get_all()
    health = DRMSManager.get_system_health()
    recent_metrics = SystemMetricsModel.get_recent(limit=15)
    return render_template(
        "dashboard.html",
        pipelines=pipelines,
        health=health,
        metrics=recent_metrics
    )


@app.route("/pipeline/<pipeline_id>")
def pipeline_detail(pipeline_id):
    """Renders the pipeline detail page with interactive Cytoscape DAG visualization."""
    pipeline = PipelineModel.get_by_id(pipeline_id)
    if not pipeline:
        return "Pipeline not found", 404

    tasks = TaskModel.get_by_pipeline(pipeline_id)
    return render_template(
        "dashboard.html",
        active_pipeline=pipeline,
        tasks=tasks,
        health=DRMSManager.get_system_health()
    )


@app.route("/job/<task_id>")
def job_detail(task_id):
    """Renders execution log inspection and stage detail for a specific task."""
    task = TaskModel.get_by_id(task_id)
    if not task:
        return "Task not found", 404

    pipeline = PipelineModel.get_by_id(task["pipeline_id"])
    log_file = Path(getattr(Config, "LOG_DIR", "logs")) / f"{task['pipeline_id']}_{task_id}.log"
    log_content = "Log file not yet generated or stage has not started."

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

@app.route("/api/health")
def api_health():
    """Returns real-time host telemetry (CPU, RAM, slots)."""
    return jsonify(DRMSManager.get_system_health())


@app.route("/api/metrics/recent")
def api_recent_metrics():
    """Returns historical CPU/RAM telemetry for dashboard charts."""
    rows = SystemMetricsModel.get_recent(limit=30)
    data = [dict(r) for r in rows]
    return jsonify(data)


@app.route("/api/pipeline/create", methods=["POST"])
def api_create_pipeline():
    """
    Submits a new EDA flow pipeline.
    Accepts JSON payload or HTML Form:
    - name: Design name (e.g. 'RISC-V Core Signoff Flow')
    - stages: Optional custom stages; defaults to standard 5-stage VLSI flow.
    """
    name = request.form.get("name") or request.json.get("name", "Standard EDA Flow") if request.is_json else request.form.get("name", "Standard EDA Flow")
    pipe_id = f"pipe-{uuid.uuid4().hex[:8]}"

    # Standard VLSI Stage Recipe
    default_stages = [
        {"id": f"{pipe_id}_synth", "name": "RTL Synthesis", "deps": []},
        {"id": f"{pipe_id}_floorplan", "name": "Floorplanning & Power Grid", "deps": [f"{pipe_id}_synth"]},
        {"id": f"{pipe_id}_placement", "name": "Standard Cell Placement", "deps": [f"{pipe_id}_floorplan"]},
        {"id": f"{pipe_id}_cts", "name": "Clock Tree Synthesis (CTS)", "deps": [f"{pipe_id}_placement"]},
        {"id": f"{pipe_id}_routing", "name": "Detailed Routing", "deps": [f"{pipe_id}_cts"]},
        {"id": f"{pipe_id}_signoff", "name": "Signoff STA & DRC", "deps": [f"{pipe_id}_routing"]},
    ]

    PipelineModel.create(pipe_id, name)
    for stage in default_stages:
        TaskModel.create(stage["id"], pipe_id, stage["name"], stage["deps"])

    logger.info(f"Created pipeline '{pipe_id}' with {len(default_stages)} stages.")

    if request.is_json:
        return jsonify({"status": "success", "pipeline_id": pipe_id}), 201
    return redirect(url_for("dashboard"))


@app.route("/api/pipeline/<pipeline_id>/dag")
def api_pipeline_dag(pipeline_id):
    """Returns Cytoscape.js formatted JSON for graph rendering."""
    try:
        data = DAGScheduler.get_dag_for_cytoscape(pipeline_id)
        return jsonify(data)
    except Exception as e:
        logger.error(f"Error generating DAG for pipeline '{pipeline_id}': {e}")
        return jsonify({"error": str(e)}), 400


@app.route("/api/pipeline/<pipeline_id>/status")
def api_pipeline_status(pipeline_id):
    """Returns status summary for live frontend polling."""
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
    """Returns execution log text for real-time log polling."""
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


# ----------------------------------------------------------------------------
# Application Startup
# ----------------------------------------------------------------------------

def start_services():
    """Initializes DB and background orchestrator."""
    global orchestrator
    DatabaseManager.init_db()
    if orchestrator is None:
        orchestrator = OrchestratorServer(poll_interval=2.0)
        orchestrator.start(blocking=False)


def main():
    """CLI entrypoint for eda-web command."""
    start_services()
    host = getattr(Config, "HOST", "127.0.0.1")
    port = getattr(Config, "PORT", 5000)
    debug = getattr(Config, "DEBUG", True)

    print("=" * 60)
    print(f"  EDA FLOW AUTOMATION - WEB GUI & API")
    print(f"  Serving dashboard at: http://{host}:{port}")
    print("=" * 60)
    app.run(host=host, port=port, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
