import os
from pathlib import Path
from dotenv import load_dotenv

# Locate project base directory
BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables from .env located at project root
load_dotenv(dotenv_path=BASE_DIR / ".env")


class Config:
    """Application configuration for EDA Flow Automation."""

    # Web & Flask Environment
    FLASK_ENV = os.getenv("FLASK_ENV", "development")
    SECRET_KEY = os.getenv("SECRET_KEY", "eda-flow-secret-key-3b91a")
    HOST = os.getenv("HOST", "127.0.0.1")
    PORT = int(os.getenv("PORT", 5000))
    DEBUG = os.getenv("DEBUG", "True").lower() in ("true", "1", "yes")

    # Logging
    LOG_LEVEL = os.getenv("LOG" \
    "_LEVEL", "INFO")
    LOG_DIR = str(BASE_DIR / os.getenv("LOG_DIR", "logs"))

    # SQLite Database
    DATABASE_PATH = str(BASE_DIR / os.getenv("DATABASE_PATH", "database/eda_flow.db"))
    DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DATABASE_PATH}")

    # Distributed Resource Management (DRMS) & Concurrency
    MAX_CONCURRENT_JOBS = int(os.getenv("MAX_CONCURRENT_JOBS", 4))
    SYSTEM_MONITOR_INTERVAL_SECS = int(os.getenv("SYSTEM_MONITOR_INTERVAL_SECS", 5))
    MAX_CPU_PERCENT = float(os.getenv("MAX_CPU_PERCENT", 85.0))
    MAX_MEMORY_PERCENT = float(os.getenv("MAX_MEMORY_PERCENT", 85.0))

    # Workspaces & Artifacts
    WORKSPACE_DIR = str(BASE_DIR / os.getenv("WORKSPACE_DIR", "workspaces"))


# Instantiate a singleton settings object
settings = Config()
