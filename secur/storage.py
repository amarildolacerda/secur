import sqlite3
import threading
from datetime import datetime
from pathlib import Path

from .config import DB_PATH


class EventStorage:
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self.connection = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.lock = threading.Lock()
        self._create_tables()

    def _create_tables(self):
        with self.lock:
            cursor = self.connection.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    camera_id TEXT NOT NULL,
                    zone TEXT,
                    event_type TEXT NOT NULL,
                    details TEXT
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS cameras (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    source TEXT NOT NULL,
                    zone TEXT
                )
                """
            )
            self.connection.commit()

    def add_event(self, camera_id: str, zone: str, event_type: str, details: str = None):
        timestamp = datetime.utcnow().isoformat() + "Z"
        with self.lock:
            cursor = self.connection.cursor()
            cursor.execute(
                "INSERT INTO events (timestamp, camera_id, zone, event_type, details) VALUES (?, ?, ?, ?, ?)",
                (timestamp, camera_id, zone, event_type, details),
            )
            self.connection.commit()
            return cursor.lastrowid

    def list_events(self, limit: int = 100):
        with self.lock:
            cursor = self.connection.cursor()
            cursor.execute(
                "SELECT id, timestamp, camera_id, zone, event_type, details FROM events ORDER BY id DESC LIMIT ?",
                (limit,),
            )
            return [dict(row) for row in cursor.fetchall()]

    def add_camera(self, name: str, source: str, zone: str = None):
        with self.lock:
            cursor = self.connection.cursor()
            cursor.execute(
                "INSERT INTO cameras (name, source, zone) VALUES (?, ?, ?)",
                (name, source, zone),
            )
            self.connection.commit()
            return cursor.lastrowid

    def list_cameras(self):
        with self.lock:
            cursor = self.connection.cursor()
            cursor.execute("SELECT id, name, source, zone FROM cameras ORDER BY id ASC")
            return [dict(row) for row in cursor.fetchall()]

    def get_camera(self, camera_id: int):
        with self.lock:
            cursor = self.connection.cursor()
            cursor.execute("SELECT id, name, source, zone FROM cameras WHERE id = ?", (camera_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def remove_camera(self, camera_id: int):
        with self.lock:
            cursor = self.connection.cursor()
            cursor.execute("DELETE FROM cameras WHERE id = ?", (camera_id,))
            self.connection.commit()
            return cursor.rowcount > 0

    def seed_cameras(self, default_cameras):
        if self.list_cameras():
            return
        for camera in default_cameras:
            self.add_camera(camera["name"], camera["source"], camera.get("zone"))

    def close(self):
        with self.lock:
            self.connection.close()
