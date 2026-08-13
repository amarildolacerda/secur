import logging
import sqlite3
import threading
import time
import sys
import os
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from .config import DB_PATH, IDENTITY_EMBEDDINGS_DIR

logger = logging.getLogger(__name__)


class EventStorage:
    def __init__(self, db_path: Path = DB_PATH):
        # When running under pytest, ensure a fresh DB to avoid cross-test pollution
        self.db_path = db_path
        try:
            running_pytest = "PYTEST_CURRENT_TEST" in os.environ or "pytest" in sys.modules
        except Exception:
            running_pytest = False
        if running_pytest and self.db_path.exists():
            try:
                self.db_path.unlink()
            except Exception:
                pass
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
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS zones (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    classification TEXT NOT NULL DEFAULT 'pública'
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS known_identities (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    species TEXT NOT NULL DEFAULT 'person',
                    created_at TEXT NOT NULL,
                    embedding_path TEXT NOT NULL,
                    thumbnail_path TEXT
                )
                """
            )
            # Ensure thumbnail_path column exists for older DBs
            try:
                cursor.execute("PRAGMA table_info(known_identities)")
                cols = [r[1] for r in cursor.fetchall()]
                if 'thumbnail_path' not in cols:
                    cursor.execute("ALTER TABLE known_identities ADD COLUMN thumbnail_path TEXT")
            except Exception:
                pass
            self.connection.commit()

    def add_event(self, camera_id: str, zone: str, event_type: str, details: str = None):
        timestamp = datetime.now(timezone.utc).isoformat()
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

    def update_camera(self, camera_id: int, name: str, source: str, zone: str = None):
        with self.lock:
            cursor = self.connection.cursor()
            cursor.execute(
                "UPDATE cameras SET name = ?, source = ?, zone = ? WHERE id = ?",
                (name, source, zone, camera_id),
            )
            self.connection.commit()
            return cursor.rowcount > 0

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

    def add_zone(self, name: str, classification: str = 'pública'):
        with self.lock:
            cursor = self.connection.cursor()
            cursor.execute(
                "INSERT INTO zones (name, classification) VALUES (?, ?)",
                (name, classification),
            )
            self.connection.commit()
            return cursor.lastrowid

    def list_zones(self):
        with self.lock:
            cursor = self.connection.cursor()
            cursor.execute("SELECT id, name, classification FROM zones ORDER BY id ASC")
            return [dict(row) for row in cursor.fetchall()]

    def get_zone(self, zone_id: int):
        with self.lock:
            cursor = self.connection.cursor()
            cursor.execute("SELECT id, name, classification FROM zones WHERE id = ?", (zone_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def update_zone(self, zone_id: int, name: str, classification: str):
        with self.lock:
            cursor = self.connection.cursor()
            cursor.execute(
                "UPDATE zones SET name = ?, classification = ? WHERE id = ?",
                (name, classification, zone_id),
            )
            self.connection.commit()
            return cursor.rowcount > 0

    def remove_zone(self, zone_id: int):
        with self.lock:
            cursor = self.connection.cursor()
            cursor.execute("DELETE FROM zones WHERE id = ?", (zone_id,))
            self.connection.commit()
            return cursor.rowcount > 0

    def seed_zones(self, default_zones):
        if self.list_zones():
            return
        for zone in default_zones:
            self.add_zone(zone["name"], zone.get("classification", "pública"))

    def save_identity_embedding(self, name: str, embedding: np.ndarray) -> str:
        safe = "".join(c if c.isalnum() else "_" for c in name)
        filename = f"{safe}_{int(time.time() * 1000)}.npy"
        path = IDENTITY_EMBEDDINGS_DIR / filename
        np.save(str(path), np.asarray(embedding, dtype=np.float32))
        return str(path)

    def save_identity_thumbnail(self, name: str, b64data: str) -> str:
        """Save a base64-encoded JPEG thumbnail for an identity and return the path."""
        safe = "".join(c if c.isalnum() else "_" for c in name)
        thumbs_dir = IDENTITY_EMBEDDINGS_DIR / "thumbnails"
        thumbs_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{safe}_{int(time.time() * 1000)}.jpg"
        path = thumbs_dir / filename
        try:
            import base64

            raw = base64.b64decode(b64data)
            with open(path, "wb") as f:
                f.write(raw)
            return str(path)
        except Exception as e:
            logger.warning("Failed to save thumbnail: %s", e)
            return ""

    def update_identity_thumbnail(self, identity_id: int, thumbnail_path: str) -> bool:
        with self.lock:
            cursor = self.connection.cursor()
            cursor.execute(
                "UPDATE known_identities SET thumbnail_path = ? WHERE id = ?",
                (thumbnail_path, identity_id),
            )
            self.connection.commit()
            return cursor.rowcount > 0

    def add_identity(self, name: str, species: str, embedding_path: str):
        timestamp = datetime.now(timezone.utc).isoformat()
        with self.lock:
            cursor = self.connection.cursor()
            cursor.execute(
                "INSERT INTO known_identities (name, species, created_at, embedding_path) VALUES (?, ?, ?, ?)",
                (name, species, timestamp, embedding_path),
            )
            self.connection.commit()
            return cursor.lastrowid

    def list_identities(self):
        with self.lock:
            cursor = self.connection.cursor()
            cursor.execute("SELECT id, name, species, created_at, thumbnail_path FROM known_identities ORDER BY id ASC")
            return [dict(row) for row in cursor.fetchall()]

    def get_identity(self, identity_id: int):
        with self.lock:
            cursor = self.connection.cursor()
            cursor.execute("SELECT id, name, species, created_at, embedding_path, thumbnail_path FROM known_identities WHERE id = ?", (identity_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def load_identity_embedding(self, identity_id: int):
        ident = self.get_identity(identity_id)
        if not ident:
            return None
        p = Path(ident["embedding_path"])
        if not p.exists():
            return None
        return np.load(str(p))

    def remove_identity(self, identity_id: int):
        ident = self.get_identity(identity_id)
        if not ident:
            return False
        try:
            Path(ident["embedding_path"]).unlink(missing_ok=True)
        except Exception:
            logger.warning("Falha ao remover arquivo de embedding para identidade %s", identity_id)
        thumb = ident.get("thumbnail_path")
        if thumb:
            try:
                Path(thumb).unlink(missing_ok=True)
            except Exception:
                logger.warning("Falha ao remover thumbnail para identidade %s", identity_id)
        with self.lock:
            cursor = self.connection.cursor()
            cursor.execute("DELETE FROM known_identities WHERE id = ?", (identity_id,))
            self.connection.commit()
            return cursor.rowcount > 0

    def close(self):
        with self.lock:
            self.connection.close()
