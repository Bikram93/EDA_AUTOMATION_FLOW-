import sqlite3
import threading
import os
from config.settings import Config

class DatabaseManager:
    _local = threading.local()

    @classmethod
    def get_db(cls):
        if not hasattr(cls._local, "connection") or cls._local.connection is None:
            # Handle path if prefix sqlite:/// is present
            db_path = Config.DATABASE_URL.replace("sqlite:///", "")
            parent_dir = os.path.dirname(db_path)
            if parent_dir:
                os.makedirs(parent_dir, exist_ok=True)

            cls._local.connection = sqlite3.connect(db_path, timeout=10.0)
            # Enable WAL mode for asynchronous concurrent read/write scalability
            cls._local.connection.execute("PRAGMA journal_mode=WAL;")
            cls._local.connection.row_factory = sqlite3.Row
        return cls._local.connection

    @classmethod
    def init_db(cls):
        db = cls.get_db()
        schema_file = "database/schema.sql"
        if not os.path.exists(schema_file):
            schema_file = os.path.join(os.path.dirname(__file__), "schema.sql")
        with open(schema_file, "r", encoding="utf-8") as f:
            db.executescript(f.read())
        db.commit()

    @classmethod
    def execute_write(cls, query, params=()):
        db = cls.get_db()
        cursor = db.cursor()
        cursor.execute(query, params)
        db.commit()
        return cursor.lastrowid

    @classmethod
    def execute_read(cls, query, params=()):
        db = cls.get_db()
        cursor = db.cursor()
        cursor.execute(query, params)
        return cursor.fetchall()

