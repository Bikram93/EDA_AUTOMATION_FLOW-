# EDA Flow Automation System

An enterprise-grade, distributed workflow automation and orchestration platform designed specifically for semiconductor and VLSI digital design flows (RTL Synthesis, Floorplanning, Placement, Clock Tree Synthesis, Routing, Signoff Timing, and Physical Verification DRC/LVS).

---

## 1. System Architecture Overview

The platform bridges high-level web control with low-level EDA tool execution, graph-based job scheduling, and hardware admission control:

```
+-------------------------------------------------------------------------+
|                       Web GUI (Flask + Jinja2)                          |
|  +--------------------+  +----------------------+  +-----------------+  |
|  |   dashboard.html   |  |   Cytoscape.js DAG   |  | job_detail.html |  |
|  |  (Health & Status) |  |   (Interactive Graph)|  |  (Live Logs)    |  |
|  +--------------------+  +----------------------+  +-----------------+  |
+------------------------------------+------------------------------------+
                                     | REST API & UI Routes
                                     v
+-------------------------------------------------------------------------+
|                      Core Engine & Orchestration                        |
|                                                                         |
|   +-------------------+  +--------------------+  +------------------+   |
|   |   src/server.py   |  |  src/scheduler.py  |  |    src/drms.py   |   |
|   | (JobOrchestrator  |->|   (NetworkX DAG    |->|  (DRMSMonitor &  |   |
|   |  Hub & Workers)   |  |    Job Engine)     |  |   Admission Ctrl)|   |
|   +-------------------+  +--------------------+  +------------------+   |
|            |                        |                       |           |
|            +------------------------+-----------------------+           |
|                                     |                                   |
|                                     v                                   |
|   +-----------------------------------------------------------------+   |
|   |              Thread-Safe SQLite Database Layer                  |   |
|   |              (WAL Mode: PRAGMA journal_mode=WAL)                |   |
|   |    - pipelines         - tasks           - system_metrics       |   |
|   +-----------------------------------------------------------------+   |
+-------------------------------------------------------------------------+
```

---

## 2. Project Directory Structure

```text
eda_flow_project/
|
|-- .env                        # Environment variables (DB path, log levels, concurrency limits)
|-- .gitignore                  # Git exclusions (venv, db, logs, agy.md, cache)
|-- README.md                   # Comprehensive project documentation & API guide
|-- requirements.txt            # Production dependencies
|-- setup.py                    # Package installation & CLI entry points
|
|-- config/                     # Configuration Management
|   |-- __init__.py             # Exports settings instance
|   `-- settings.py             # Parses .env with fallback defaults & path anchors
|
|-- database/                   # SQLite Database Layer
|   |-- __init__.py             # Exports DatabaseManager & Models
|   |-- connection.py           # Thread-safe SQLite connection manager with WAL mode
|   |-- models.py               # Data Access Objects (PipelineModel, TaskModel, SystemMetricsModel)
|   |-- schema.sql              # Relational DDL definitions
|   `-- eda_flow.db             # Active SQLite database file
|
|-- src/                        # Core Application Backend
|   |-- __init__.py
|   |-- server.py               # Central Hub / JobOrchestrator (Coordinates workers)
|   |-- drms.py                 # Distributed Resource Management (DRMSMonitor, node limits)
|   |-- scheduler.py            # DAG Job Engine (NetworkX pipeline parser & runner)
|   `-- utils/                  # Shared backend utilities
|       |-- __init__.py
|       `-- logger.py           # Structured production logger
|
`-- web/                        # Front-End Web GUI (Flask + Jinja2)
    |-- __init__.py
    |-- app.py                  # Flask Application entry point & route definitions
    |-- static/                 # Static Assets (UI Styling & Cytoscape graphs)
    |   |-- css/
    |   |   `-- style.css       # Clean dark/light theme for VLSI dashboards
    |   `-- js/
    |       `-- main.js         # Cytoscape.js DAG visualization & live polling
    `-- templates/              # Jinja2 HTML Templates
        |-- base.html           # Main boilerplate layout & Cytoscape CDN
        |-- dashboard.html      # Central dashboard (DAG visualizer, health metrics)
        `-- job_detail.html     # Deep dive into specific execution logs
```

---

## 3. Technology Stack & Key Decisions

| Component | Technology | Rationale |
| :--- | :--- | :--- |
| **Web Server** | Flask 3.0.3, Jinja2 3.1.4 | Lightweight WSGI microframework for high-performance operational dashboards. |
| **DAG Scheduling** | NetworkX 3.3 | Graph manipulation engine for cycle validation, topological order, and failure cascading. |
| **Resource Monitor** | psutil 5.9.8 | Cross-platform hardware telemetry (CPU %, memory %) enabling dynamic admission control (DRMS). |
| **Database** | SQLite 3 (WAL Mode) | Zero-maintenance embedded database. Write-Ahead Logging (`WAL`) allows concurrent reads during writes. |
| **Frontend Graphs** | Cytoscape.js | High-performance graph theory library supporting hierarchical DAG rendering and interactive node inspection. |
| **Data Analytics** | Pandas 2.2.2 | Ingests and summarizes execution metrics, runtime timelines, and Quality of Results (QoR). |

---

## 4. REST API Reference (Inputs & Expected Outputs)

### 4.1. Submit a New Pipeline (`POST /pipeline/submit` or `POST /api/pipeline/create`)
Submits a new EDA workflow. Spawns standard stages: RTL Synthesis &rarr; Floorplanning &rarr; Place & Route &rarr; Parallel (DRC & LVS).

- **URL**: `/pipeline/submit`
- **Method**: `POST`
- **Headers**: `Content-Type: application/json`

#### Sample Input (cURL):
```bash
curl -X POST http://127.0.0.1:5000/pipeline/submit      -H "Content-Type: application/json"      -d '{"name": "RISC-V 32b Core Synthesis Run"}'
```

#### Expected Output (Status: `201 Created`):
```json
{
  "pipeline_id": "pipe_767acf49",
  "pipeline_name": "RISC-V 32b Core Synthesis Run",
  "status": "success",
  "task_count": 5
}
```

---

### 4.2. Fetch Interactive Cytoscape DAG (`GET /api/pipeline/<pipeline_id>/graph`)
Retrieves the mathematical graph structure serialized for Cytoscape.js.

- **URL**: `/api/pipeline/<pipeline_id>/graph`
- **Method**: `GET`

#### Sample Input (cURL):
```bash
curl -X GET http://127.0.0.1:5000/api/pipeline/pipe_767acf49/graph
```

#### Expected Output (Status: `200 OK`):
```json
[
  {
    "data": {
      "id": "syn_pipe_767acf49",
      "label": "RTL Synthesis (COMPLETED)",
      "name": "RTL Synthesis",
      "status": "COMPLETED"
    }
  },
  {
    "data": {
      "id": "floorplan_pipe_767acf49",
      "label": "Floorplanning (RUNNING)",
      "name": "Floorplanning",
      "status": "RUNNING"
    }
  },
  {
    "data": {
      "id": "syn_pipe_767acf49->floorplan_pipe_767acf49",
      "source": "syn_pipe_767acf49",
      "target": "floorplan_pipe_767acf49"
    }
  }
]
```

---

### 4.3. Real-Time Pipeline Status (`GET /api/pipeline/<pipeline_id>/status`)
Polled by frontend controllers to update status badges in real time.

- **URL**: `/api/pipeline/<pipeline_id>/status`
- **Method**: `GET`

#### Sample Input (cURL):
```bash
curl -X GET http://127.0.0.1:5000/api/pipeline/pipe_767acf49/status
```

#### Expected Output (Status: `200 OK`):
```json
{
  "pipeline": {
    "created_at": "2026-09-08 23:00:30",
    "id": "pipe_767acf49",
    "name": "RISC-V 32b Core Synthesis Run",
    "status": "RUNNING"
  },
  "tasks": [
    {
      "dependencies": "",
      "ended_at": "2026-09-08 23:00:34",
      "id": "syn_pipe_767acf49",
      "name": "RTL Synthesis",
      "pipeline_id": "pipe_767acf49",
      "started_at": "2026-09-08 23:00:30",
      "status": "COMPLETED"
    },
    {
      "dependencies": "syn_pipe_767acf49",
      "ended_at": null,
      "id": "floorplan_pipe_767acf49",
      "name": "Floorplanning",
      "pipeline_id": "pipe_767acf49",
      "started_at": "2026-09-08 23:00:34",
      "status": "RUNNING"
    }
  ]
}
```

---

### 4.4. DRMS Host Health Telemetry (`GET /api/health`)
Returns live host CPU, memory, and concurrency slot utilization.

- **URL**: `/api/health`
- **Method**: `GET`

#### Sample Input (cURL):
```bash
curl -X GET http://127.0.0.1:5000/api/health
```

#### Expected Output (Status: `200 OK`):
```json
{
  "active_jobs": 1,
  "available_slots": 3,
  "cpu_utilization": 18.4,
  "max_jobs": 4,
  "memory_utilization": 72.1
}
```

---

### 4.5. Stream Task Execution Logs (`GET /api/job/<task_id>/logs`)
Returns stdout/stderr logs for a specific EDA stage.

- **URL**: `/api/job/<task_id>/logs`
- **Method**: `GET`

#### Sample Input (cURL):
```bash
curl -X GET http://127.0.0.1:5000/api/job/syn_pipe_767acf49/logs
```

#### Expected Output (Status: `200 OK`):
```json
{
  "logs": "=== EDA Task Execution: RTL Synthesis (syn_pipe_767acf49) ===
Pipeline: pipe_767acf49
Started at: 2026-09-08 23:00:30

[INFO] Initializing EDA tool environment for RTL Synthesis...
[INFO] Processing stage inputs and geometry...
[INFO] Running design rule and timing checks...
[INFO] Stage RTL Synthesis completed with 0 errors.
Ended at: 2026-09-08 23:00:34
"
}
```

---

## 5. Quickstart & Operational Usage Guide

### 5.1. Activate the Python Virtual Environment
```powershell
# In PowerShell (Windows)
.\venv\Scripts\Activate.ps1

# In Command Prompt (Windows)
venv\Scripts\activate.bat

# In Linux / macOS
source venv/bin/activate
```

### 5.2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 5.3. Launch the Application
```bash
python -m web.app
```
*(This single command initializes SQLite, spawns the DRMS telemetry daemon, launches the background Orchestrator loop, and serves the Web GUI).*

Now open your browser and navigate to:
👉 **`http://127.0.0.1:5000`**

---

### 5.4. Dashboard User Walkthrough

#### Step 1: Monitor Real-Time System Telemetry
At the top of the dashboard, you will see 4 live metric cards:
- **Host CPU Load**: Real-time CPU percentage sampled via `psutil`.
- **Host RAM Usage**: Real-time memory allocation percentage.
- **Worker Slots**: Active jobs vs maximum slot capacity (`Active / Max`).
- **Total Pipelines**: Number of completed or ongoing flow runs.

#### Step 2: Launch a New EDA Flow Run
1. In the **"Launch New EDA Pipeline"** card, type a design name (e.g. `RISC-V 32b Core Tapeout`).
2. Click **"Launch Pipeline Run"**.
3. The platform dispatches a 5-stage VLSI design flow:
   ```text
   RTL Synthesis ──► Floorplanning ──► Place & Route ──┬──► Design Rule Check (DRC)
                                                       └──► Layout Vs Schematic (LVS)
   ```

#### Step 3: Inspect Interactive Cytoscape.js DAG
1. In the **"Pipeline History"** table, click **"Inspect DAG"** on your flow.
2. An interactive graph will render showing all stages and dependency arrows:
   - 🔵 **Blue (Pulsing)**: `RUNNING` (Stage currently active in worker thread)
   - 🟢 **Green**: `COMPLETED` (Stage finished successfully with 0 errors)
   - 🟠 **Orange**: `SKIPPED` (Downstream stage skipped due to parent failure)
   - 🔴 **Red**: `FAILED` (Stage encountered syntax or design violation error)
   - ⚪ **Gray**: `PENDING` (Waiting for predecessor stages to finish)

#### Step 4: Stream Live Execution Logs
1. In the stage table below the DAG, click **"View Logs"** (or click directly on any graph node).
2. You will enter the **Job Detail Terminal View**, which automatically polls stdout/stderr every 2 seconds and streams live tool execution output.

---

### 5.5. Running the Background Orchestrator Standalone (CLI Mode)
If you wish to run the backend scheduler without the web interface:
```bash
python -m src.server
# Or using the installed console script:
eda-server
```

---

## 6. Development Workflow & Status

- [x] Virtual environment & dependencies installed
- [x] Configuration management (`config/settings.py`)
- [x] Database schema & thread-safe SQLite connection (`database/`)
- [x] Models for pipelines, tasks, and system metrics (`database/models.py`)
- [x] Structured logging utility (`src/utils/logger.py`)
- [x] Distributed Resource Management System (`src/drms.py`)
- [x] NetworkX DAG scheduler engine (`src/scheduler.py`)
- [x] Central Hub orchestrator daemon (`src/server.py`)
- [x] Flask web interface & Cytoscape.js DAG visualization (`web/`)
