# EDA Flow Automation System

An enterprise-grade, distributed workflow automation and orchestration platform designed specifically for semiconductor and VLSI digital design flows (RTL Synthesis, Floorplanning, Placement, Clock Tree Synthesis, Routing, and Signoff Timing/DRC).

---

## 1. System Architecture Overview

The system bridges low-level EDA tool execution with modern web-based monitoring, DAG dependency resolution, and resource allocation:

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
|   |   (Central Hub /  |->|   (NetworkX DAG    |->|   (Distributed   |   |
|   |    Orchestrator)  |  |    Job Engine)     |  |  Resource Mgr)   |   |
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
|-- .env                        # Environment variables (DB path, log levels, concurrency)
|-- .gitignore                  # Git exclusions (venv, db, logs, workspaces)
|-- README.md                   # Comprehensive project documentation
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
|   |-- server.py               # Central Hub / Orchestrator (Coordinates workers)
|   |-- drms.py                 # Distributed Resource Management (System health, node limits)
|   |-- scheduler.py            # DAG Job Engine (NetworkX pipeline parser & runner)
|   `-- utils/                  # Shared backend utilities
|       |-- __init__.py
|       `-- logger.py           # Structured multi-handler production logger
|
`-- web/                        # Front-End Web GUI (Flask + Jinja2)
    |-- __init__.py
    |-- app.py                  # Flask Application entry point & route definitions
    |-- static/                 # Static Assets (UI Styling & High-performance graphs)
    |   |-- css/
    |   |   `-- style.css       # Clean dark/light theme for VLSI dashboards
    |   `-- js/
    |       `-- main.js         # Cytoscape.js DAG visualization & live polling
    `-- templates/              # Jinja2 HTML Templates
        |-- base.html           # Main boilerplate layout
        |-- dashboard.html      # Central layout view (DAG visualization, health metrics)
        `-- job_detail.html     # Deep dive into specific execution logs
```

---

## 3. Technology Stack & Key Decisions

| Component | Technology | Rationale |
| :--- | :--- | :--- |
| **Web Server** | Flask 3.0.3, Jinja2 3.1.4 | Lightweight, production-proven WSGI microframework suitable for low-latency operational dashboards. |
| **DAG Scheduling** | NetworkX 3.3 | Mathematical graph manipulation engine for cycle detection, topological sorting, and upstream dependency resolution. |
| **Resource Monitor** | psutil 5.9.8 | Cross-platform hardware telemetry (CPU %, memory %, core counts) enabling dynamic admission control (DRMS). |
| **Database** | SQLite 3 (WAL Mode) | Zero-maintenance embedded relational database. Write-Ahead Logging (WAL) allows concurrent reads without locking writers. |
| **Frontend Graphs** | Cytoscape.js | High-performance graph theory library supporting hierarchical DAG rendering and interactive node inspection. |
| **Data Analytics** | Pandas 2.2.2 | Ingests and summarizes execution metrics, runtime timelines, and Quality of Results (QoR). |

---

## 4. Detailed Component Breakdown

### 4.1. Configuration Layer (`config/`)
- **`config/settings.py`**:
  - Uses `python-dotenv` to parse environment variables from `.env`.
  - Defines `BASE_DIR` dynamically so relative paths work regardless of execution directory.
  - Controls parameters such as `MAX_CONCURRENT_JOBS` (default: 4) and `SYSTEM_MONITOR_INTERVAL_SECS` (default: 5).

### 4.2. Database Layer (`database/`)
- **`database/schema.sql`**:
  - `pipelines`: Tracks top-level flow executions (e.g. `riscv_core_flow`).
  - `tasks`: Represents each stage (`Synthesis`, `Floorplan`, `Placement`, `CTS`, `Routing`, `STA`). Contains `dependencies` stored as comma-separated task IDs.
  - `system_metrics`: Stores periodic CPU and RAM utilization metrics collected by the DRMS.
- **`database/connection.py`**:
  - `DatabaseManager`: Implements thread-local storage (`threading.local()`) so worker threads do not share connections.
  - Enables `PRAGMA journal_mode=WAL;` and `sqlite3.Row` for fast, dictionary-style row access.
- **`database/models.py`**:
  - `PipelineModel`: `create()`, `update_status()`, `get_all()`, `get_by_id()`
  - `TaskModel`: `create()`, `update_status()`, `get_by_pipeline()`, `get_by_id()`
  - `SystemMetricsModel`: `record()`, `get_recent()`

### 4.3. Core Backend Engine (`src/`)
- **`src/utils/logger.py`**:
  - Multi-target logging (rotating files in `logs/` + colorized console output).
- **`src/drms.py` (Distributed Resource Management System)**:
  - Telemetry daemon that samples host CPU and RAM.
  - Prevents server crashes by enforcing admission control: jobs are only dispatched if system utilization stays below thresholds (`MAX_CPU_PERCENT`, `MAX_MEMORY_PERCENT`).
- **`src/scheduler.py` (DAG Engine)**:
  - Parses stage dependency strings into a `networkx.DiGraph`.
  - Computes ready tasks whose parent dependencies have status `COMPLETED`.
  - Cascades `SKIPPED` status to downstream tasks if an upstream parent stage fails (e.g. syntax error in Synthesis skips Routing).
- **`src/server.py` (Central Hub / Orchestrator)**:
  - Heartbeat coordination loop: periodically polls ready tasks, verifies DRMS slot capacity, dispatches child worker processes, redirects stdout/stderr to task-specific log files, and updates database records.

### 4.4. Web GUI (`web/`)
- **`web/app.py`**:
  - Flask endpoints for dashboard rendering, pipeline submission, and live JSON telemetry (`/api/metrics`, `/api/pipeline/<id>/dag`).
- **`web/static/js/main.js`**:
  - Powers interactive Cytoscape DAG graphs:
    - **Grey**: `PENDING`
    - **Blue**: `RUNNING`
    - **Green**: `COMPLETED`
    - **Red**: `FAILED`
    - **Orange**: `SKIPPED`
- **`web/templates/`**:
  - Semantic HTML5 templates styled with responsive dark/light CSS.

---

## 5. Quickstart Guide

### 5.1. Environment Activation
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

### 5.3. Initialize the Database
```python
from database.connection import DatabaseManager
DatabaseManager.init_db()
```

### 5.4. Launch the Web Dashboard
```bash
python -m web.app
```
Open your browser and navigate to: `http://127.0.0.1:5000`

---

## 6. Development Workflow & Status

- [x] Virtual environment & dependencies installed
- [x] Configuration management (`config/settings.py`)
- [x] Database schema & thread-safe SQLite connection (`database/`)
- [x] Models for pipelines, tasks, and system metrics (`database/models.py`)
- [x] Structured logging utility (`src/utils/logger.py`)
- [x] Distributed Resource Management System (`src/drms.py`)
- [x] NetworkX DAG scheduler engine (`src/scheduler.py`)
- [ ] Central Hub orchestrator daemon (`src/server.py`) [In Progress on dev_serv]
- [ ] Flask web interface & Cytoscape.js DAG visualization (`web/`)
