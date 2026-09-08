CREATE TABLE IF NOT EXISTS pipelines (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  status TEXT NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS tasks (
  id TEXT PRIMARY KEY,
  pipeline_id TEXT NOT NULL,
  name TEXT NOT NULL,
  status TEXT NOT NULL,
  dependencies TEXT, -- Comma-separated task IDs
  started_at TIMESTAMP,
  ended_at TIMESTAMP,
  FOREIGN KEY(pipeline_id) REFERENCES pipelines(id)
);

CREATE TABLE IF NOT EXISTS system_metrics (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  cpu_utilization REAL,
  memory_utilization REAL,
  timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
