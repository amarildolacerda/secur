import logging
import json
import sqlite3
import threading
import time
import sys
import os
import shutil
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
                    zone TEXT,
                    alert_classes TEXT,
                    exclusion_zones TEXT
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS zones (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    classification TEXT NOT NULL DEFAULT 'pública',
                    schedule TEXT
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
            # Ensure new camera columns exist for older DBs
            try:
                cursor.execute("PRAGMA table_info(cameras)")
                cols = [r[1] for r in cursor.fetchall()]
                if 'alert_classes' not in cols:
                    cursor.execute("ALTER TABLE cameras ADD COLUMN alert_classes TEXT")
                if 'exclusion_zones' not in cols:
                    cursor.execute("ALTER TABLE cameras ADD COLUMN exclusion_zones TEXT")
                if 'mask_polygons' not in cols:
                    cursor.execute("ALTER TABLE cameras ADD COLUMN mask_polygons TEXT")
            except Exception:
                pass
            # Ensure schedule column exists for older DBs
            try:
                cursor.execute("PRAGMA table_info(zones)")
                cols = [r[1] for r in cursor.fetchall()]
                if 'schedule' not in cols:
                    cursor.execute("ALTER TABLE zones ADD COLUMN schedule TEXT")
            except Exception:
                pass
            # Ensure clip_path column exists for older DBs
            try:
                cursor.execute("PRAGMA table_info(events)")
                cols = [r[1] for r in cursor.fetchall()]
                if 'clip_path' not in cols:
                    cursor.execute("ALTER TABLE events ADD COLUMN clip_path TEXT")
            except Exception:
                pass
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS camera_thumbnails (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    camera_id INTEGER NOT NULL,
                    timestamp TEXT NOT NULL,
                    event_type TEXT,
                    path TEXT NOT NULL
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS event_clips (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    camera_id INTEGER NOT NULL,
                    event_id INTEGER,
                    timestamp TEXT NOT NULL,
                    path TEXT NOT NULL,
                    duration_s REAL
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS notification_routing (
                    channel TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    PRIMARY KEY (channel, event_type)
                )
                """
            )
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
                "SELECT id, timestamp, camera_id, zone, event_type, details, clip_path FROM events ORDER BY id DESC LIMIT ?",
                (limit,),
            )
            return [dict(row) for row in cursor.fetchall()]

    def add_camera(self, name: str, source: str, zone: str = None, alert_classes=None, exclusion_zones=None, mask_polygons=None):
        with self.lock:
            cursor = self.connection.cursor()
            cursor.execute(
                "INSERT INTO cameras (name, source, zone, alert_classes, exclusion_zones, mask_polygons) VALUES (?, ?, ?, ?, ?, ?)",
                (name, source, zone,
                 json.dumps(alert_classes) if alert_classes else None,
                 json.dumps(exclusion_zones) if exclusion_zones else None,
                 json.dumps(mask_polygons) if mask_polygons else None),
            )
            self.connection.commit()
            return cursor.lastrowid

    def list_cameras(self):
        with self.lock:
            cursor = self.connection.cursor()
            cursor.execute("SELECT id, name, source, zone, alert_classes, exclusion_zones, mask_polygons FROM cameras ORDER BY id ASC")
            rows = [dict(row) for row in cursor.fetchall()]
        for row in rows:
            row["alert_classes"] = json.loads(row["alert_classes"]) if row.get("alert_classes") else None
            row["exclusion_zones"] = json.loads(row["exclusion_zones"]) if row.get("exclusion_zones") else None
            row["mask_polygons"] = json.loads(row["mask_polygons"]) if row.get("mask_polygons") else None
        return rows

    def get_camera(self, camera_id: int):
        with self.lock:
            cursor = self.connection.cursor()
            cursor.execute("SELECT id, name, source, zone, alert_classes, exclusion_zones, mask_polygons FROM cameras WHERE id = ?", (camera_id,))
            row = cursor.fetchone()
            if not row:
                return None
            camera = dict(row)
        camera["alert_classes"] = json.loads(camera["alert_classes"]) if camera.get("alert_classes") else None
        camera["exclusion_zones"] = json.loads(camera["exclusion_zones"]) if camera.get("exclusion_zones") else None
        camera["mask_polygons"] = json.loads(camera["mask_polygons"]) if camera.get("mask_polygons") else None
        return camera

    def update_camera(self, camera_id: int, name: str, source: str, zone: str = None, alert_classes=None, exclusion_zones=None, mask_polygons=None):
        with self.lock:
            cursor = self.connection.cursor()
            cursor.execute(
                "UPDATE cameras SET name = ?, source = ?, zone = ?, alert_classes = ?, exclusion_zones = ?, mask_polygons = ? WHERE id = ?",
                (name, source, zone,
                 json.dumps(alert_classes) if alert_classes else None,
                 json.dumps(exclusion_zones) if exclusion_zones else None,
                 json.dumps(mask_polygons) if mask_polygons else None,
                 camera_id),
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

    def add_zone(self, name: str, classification: str = 'pública', schedule=None):
        with self.lock:
            cursor = self.connection.cursor()
            cursor.execute(
                "INSERT INTO zones (name, classification, schedule) VALUES (?, ?, ?)",
                (name, classification, json.dumps(schedule) if schedule else None),
            )
            self.connection.commit()
            return cursor.lastrowid

    def list_zones(self):
        with self.lock:
            cursor = self.connection.cursor()
            cursor.execute("SELECT id, name, classification, schedule FROM zones ORDER BY id ASC")
            rows = [dict(row) for row in cursor.fetchall()]
        for row in rows:
            row["schedule"] = json.loads(row["schedule"]) if row.get("schedule") else None
        return rows

    def get_zone(self, zone_id: int):
        with self.lock:
            cursor = self.connection.cursor()
            cursor.execute("SELECT id, name, classification, schedule FROM zones WHERE id = ?", (zone_id,))
            row = cursor.fetchone()
            if not row:
                return None
            zone = dict(row)
        zone["schedule"] = json.loads(zone["schedule"]) if zone.get("schedule") else None
        return zone

    def update_zone(self, zone_id: int, name: str, classification: str, schedule=None):
        with self.lock:
            cursor = self.connection.cursor()
            cursor.execute(
                "UPDATE zones SET name = ?, classification = ?, schedule = ? WHERE id = ?",
                (name, classification, json.dumps(schedule) if schedule else None, zone_id),
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

    def add_camera_thumbnail(self, camera_id: int, path: str, event_type: str) -> int:
        timestamp = datetime.now(timezone.utc).isoformat()
        with self.lock:
            cursor = self.connection.cursor()
            cursor.execute(
                "INSERT INTO camera_thumbnails (camera_id, timestamp, event_type, path) VALUES (?, ?, ?, ?)",
                (camera_id, timestamp, event_type, path),
            )
            self.connection.commit()
            return cursor.lastrowid

    def list_camera_thumbnails(self, camera_id: int, limit: int = 20):
        with self.lock:
            cursor = self.connection.cursor()
            cursor.execute(
                "SELECT id, timestamp, camera_id, event_type, path FROM camera_thumbnails "
                "WHERE camera_id = ? ORDER BY id DESC LIMIT ?",
                (camera_id, limit),
            )
            return [dict(row) for row in cursor.fetchall()]

    def prune_camera_thumbnails(self, camera_id: int, keep: int = 20):
        with self.lock:
            cursor = self.connection.cursor()
            cursor.execute(
                "SELECT id, path FROM camera_thumbnails WHERE camera_id = ? ORDER BY id DESC LIMIT -1 OFFSET ?",
                (camera_id, keep),
            )
            excess = [dict(row) for row in cursor.fetchall()]
            for item in excess:
                try:
                    Path(item["path"]).unlink(missing_ok=True)
                except Exception:
                    logger.warning("Falha ao remover thumbnail %s", item["path"])
                cursor.execute("DELETE FROM camera_thumbnails WHERE id = ?", (item["id"],))
            self.connection.commit()

    def remove_camera_thumbnails(self, camera_id: int):
        with self.lock:
            cursor = self.connection.cursor()
            cursor.execute("SELECT path FROM camera_thumbnails WHERE camera_id = ?", (camera_id,))
            rows = cursor.fetchall()
            for row in rows:
                try:
                    Path(row["path"]).unlink(missing_ok=True)
                except Exception:
                    logger.warning("Falha ao remover thumbnail %s", row["path"])
            cursor.execute("DELETE FROM camera_thumbnails WHERE camera_id = ?", (camera_id,))
            self.connection.commit()

    def get_camera_thumbnail(self, thumb_id: int):
        with self.lock:
            cursor = self.connection.cursor()
            cursor.execute(
                "SELECT id, camera_id, timestamp, event_type, path FROM camera_thumbnails WHERE id = ?",
                (thumb_id,),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def add_event_clip(self, camera_id: int, event_id, path: str, duration_s: float) -> int:
        timestamp = datetime.now(timezone.utc).isoformat()
        with self.lock:
            cursor = self.connection.cursor()
            cursor.execute(
                "INSERT INTO event_clips (camera_id, event_id, timestamp, path, duration_s) VALUES (?, ?, ?, ?, ?)",
                (camera_id, event_id, timestamp, path, duration_s),
            )
            self.connection.commit()
            return cursor.lastrowid

    def list_event_clips(self, camera_id: int, limit: int = 20):
        with self.lock:
            cursor = self.connection.cursor()
            cursor.execute(
                "SELECT id, camera_id, event_id, timestamp, path, duration_s FROM event_clips "
                "WHERE camera_id = ? ORDER BY id DESC LIMIT ?",
                (camera_id, limit),
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_event_clip(self, clip_id: int):
        with self.lock:
            cursor = self.connection.cursor()
            cursor.execute(
                "SELECT id, camera_id, event_id, timestamp, path, duration_s FROM event_clips WHERE id = ?",
                (clip_id,),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def prune_event_clips(self, camera_id: int, keep: int = 20):
        with self.lock:
            cursor = self.connection.cursor()
            cursor.execute(
                "SELECT id, path FROM event_clips WHERE camera_id = ? ORDER BY id DESC LIMIT -1 OFFSET ?",
                (camera_id, keep),
            )
            excess = [dict(row) for row in cursor.fetchall()]
            for item in excess:
                try:
                    Path(item["path"]).unlink(missing_ok=True)
                except Exception:
                    logger.warning("Falha ao remover clipe %s", item["path"])
                cursor.execute("DELETE FROM event_clips WHERE id = ?", (item["id"],))
            self.connection.commit()

    def remove_event_clips(self, camera_id: int):
        with self.lock:
            cursor = self.connection.cursor()
            cursor.execute("SELECT path FROM event_clips WHERE camera_id = ?", (camera_id,))
            rows = cursor.fetchall()
            for row in rows:
                try:
                    Path(row["path"]).unlink(missing_ok=True)
                except Exception:
                    logger.warning("Falha ao remover clipe %s", row["path"])
            cursor.execute("DELETE FROM event_clips WHERE camera_id = ?", (camera_id,))
            self.connection.commit()

    def update_event_clip_path(self, event_id: int, clip_path: str) -> bool:
        with self.lock:
            cursor = self.connection.cursor()
            cursor.execute(
                "UPDATE events SET clip_path = ? WHERE id = ?",
                (clip_path, event_id),
            )
            self.connection.commit()
            return cursor.rowcount > 0

    def get_routing(self, channel: str) -> dict:
        with self.lock:
            cursor = self.connection.cursor()
            cursor.execute(
                "SELECT event_type, enabled FROM notification_routing WHERE channel = ?",
                (channel,),
            )
            return {row["event_type"]: bool(row["enabled"]) for row in cursor.fetchall()}

    def set_routing(self, channel: str, event_type: str, enabled: bool):
        with self.lock:
            cursor = self.connection.cursor()
            cursor.execute(
                "INSERT INTO notification_routing (channel, event_type, enabled) VALUES (?, ?, ?) "
                "ON CONFLICT(channel, event_type) DO UPDATE SET enabled = excluded.enabled",
                (channel, event_type, int(enabled)),
            )
            self.connection.commit()

    def get_all_routing(self) -> dict:
        with self.lock:
            cursor = self.connection.cursor()
            cursor.execute("SELECT channel, event_type, enabled FROM notification_routing")
            routing = {}
            for row in cursor.fetchall():
                routing.setdefault(row["channel"], {})[row["event_type"]] = bool(row["enabled"])
            return routing

    def seed_default_routing(self, defaults: dict):
        with self.lock:
            cursor = self.connection.cursor()
            cursor.execute("SELECT COUNT(*) AS c FROM notification_routing")
            if cursor.fetchone()["c"] > 0:
                return
            for channel, events in defaults.items():
                for event_type, enabled in events.items():
                    cursor.execute(
                        "INSERT INTO notification_routing (channel, event_type, enabled) VALUES (?, ?, ?)",
                        (channel, event_type, int(enabled)),
                    )
            self.connection.commit()

    def close(self):
        with self.lock:
            self.connection.close()
