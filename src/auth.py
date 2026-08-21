"""
Authentication and authorization module for Secur.

Provides:
- Password hashing (PBKDF2-SHA256 via werkzeug)
- Session token generation and validation
- Permission checking with in-memory cache
- Decorators: require_auth, require_permission
- Rate limiting for login attempts
"""

import functools
import hashlib
import logging
import secrets
import time
from datetime import datetime, timezone, timedelta

from flask import request, jsonify, g, session

logger = logging.getLogger(__name__)


# ── Password hashing ────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    """Hash a password using PBKDF2-SHA256 (werkzeug)."""
    from werkzeug.security import generate_password_hash
    return generate_password_hash(password, method="pbkdf2:sha256:600000")


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against its hash."""
    from werkzeug.security import check_password_hash
    return check_password_hash(password_hash, password)


# ── Session tokens ──────────────────────────────────────────────────────

def generate_session_token() -> str:
    """Generate a cryptographically secure 64-char hex token."""
    return secrets.token_hex(32)


def create_session(storage, user_id: int, ip_address=None, ttl_hours=24) -> str:
    """Create a new session and return the token."""
    token = generate_session_token()
    now = datetime.now(timezone.utc)
    expires = now + timedelta(hours=ttl_hours)
    storage.create_session(token, user_id, expires.isoformat(), ip_address)
    return token


def validate_session(storage, token: str) -> dict | None:
    """Validate a session token. Returns user dict or None."""
    if not token:
        return None
    sess = storage.get_session(token)
    if not sess:
        return None
    # Check expiry
    try:
        expires = datetime.fromisoformat(sess["expires_at"])
        if datetime.now(timezone.utc) > expires:
            storage.delete_session(token)
            return None
    except (ValueError, TypeError):
        storage.delete_session(token)
        return None
    # Load user
    user = storage.get_user(sess["user_id"])
    if not user or not user.get("active"):
        storage.delete_session(token)
        return None
    return user


# ── Permission system ───────────────────────────────────────────────────

# All available permissions with human labels
PERMISSIONS = {
    "view_live":              "Ver câmeras ao vivo",
    "view_events":            "Ver histórico de eventos",
    "view_clips":             "Ver clipes de vídeo",
    "view_snapshots":         "Ver snapshots/thumbnails",
    "view_dashboard":         "Acessar dashboard",
    "dismiss_event":          "Dispensar/acknowledge evento",
    "retain_event":           "Retener evento (proteger de prune)",
    "delete_event":           "Deletar evento",
    "prune_events":           "Podar eventos antigos",
    "arm_disarm":             "Armar/desarmar câmeras e zonas",
    "manage_cameras":         "Adicionar/editar/deletar câmeras",
    "manage_zones":           "Adicionar/editar/deletar zonas",
    "manage_identities":      "Gerenciar identidades (faces)",
    "manage_notifications":   "Configurar notificações/routing",
    "manage_settings":        "Alterar configurações gerais",
    "manage_retention":       "Configurar política de retenção",
    "manage_users":           "Gerenciar todos os usuários",
    "create_users":           "Criar novos usuários",
    "view_users":             "Listar usuários",
    "manage_permissions":     "Configurar permissões por role",
    "view_audit_log":         "Ver log de auditoria",
}

# Default permissions per role (seeded on first run)
DEFAULT_ROLE_PERMISSIONS = {
    "admin": {k: True for k in PERMISSIONS},
    "chefe_seguranca": {
        "view_live": True, "view_events": True, "view_clips": True,
        "view_snapshots": True, "view_dashboard": True,
        "dismiss_event": True, "retain_event": True,
        "arm_disarm": True,
        "create_users": True, "view_users": True,
        "view_audit_log": True,
    },
    "vigilante": {
        "view_live": True, "view_events": True, "view_clips": True,
        "view_snapshots": True, "view_dashboard": True,
        "dismiss_event": True, "retain_event": True,
        "arm_disarm": True,
    },
    "viewer": {
        "view_live": True, "view_events": True, "view_clips": True,
        "view_snapshots": True, "view_dashboard": True,
    },
}

# Roles that can be created by each role
CAN_CREATE_ROLES = {
    "admin":             ["admin", "chefe_seguranca", "vigilante", "viewer"],
    "chefe_seguranca":   ["chefe_seguranca", "vigilante", "viewer"],
}


class PermissionCache:
    """In-memory cache for role permissions, with TTL-based invalidation."""

    def __init__(self, ttl_seconds=5):
        self._cache = {}  # role -> (permissions_dict, timestamp)
        self._ttl = ttl_seconds

    def get(self, storage, role: str) -> dict:
        now = time.time()
        cached = self._cache.get(role)
        if cached and (now - cached[1]) < self._ttl:
            return cached[0]
        # Reload from DB
        perms = storage.get_role_permissions(role)
        self._cache[role] = (perms, now)
        return perms

    def invalidate(self, role=None):
        if role:
            self._cache.pop(role, None)
        else:
            self._cache.clear()


# Global cache instance
_permission_cache = PermissionCache()


def has_permission(storage, role: str, permission: str) -> bool:
    """Check if a role has a specific permission (uses cache)."""
    perms = _permission_cache.get(storage, role)
    return perms.get(permission, False)


def invalidate_permission_cache(role=None):
    """Call after modifying role_permissions."""
    _permission_cache.invalidate(role)


# ── Rate limiting for login ────────────────────────────────────────────

class LoginRateLimiter:
    """Simple in-memory rate limiter: max attempts per IP within a window."""

    def __init__(self, max_attempts=5, window_seconds=60, lockout_seconds=300):
        self._attempts = {}  # ip -> [(timestamp, ...)]
        self._lockouts = {}  # ip -> lockout_expiry
        self._max = max_attempts
        self._window = window_seconds
        self._lockout = lockout_seconds

    def is_locked(self, ip: str) -> bool:
        expiry = self._lockouts.get(ip)
        if expiry and time.time() < expiry:
            return True
        if expiry:
            del self._lockouts[ip]
        return False

    def record_failure(self, ip: str):
        now = time.time()
        attempts = self._attempts.setdefault(ip, [])
        # Prune old attempts outside window
        attempts[:] = [t for t in attempts if (now - t) < self._window]
        attempts.append(now)
        if len(attempts) >= self._max:
            self._lockouts[ip] = now + self._lockout
            logger.warning("Rate limit: IP %s locked out for %ds", ip, self._lockout)

    def record_success(self, ip: str):
        self._attempts.pop(ip, None)
        self._lockouts.pop(ip, None)


_rate_limiter = None  # Initialized in setup_auth


# ── Flask decorators ───────────────────────────────────────────────────

def require_auth(f):
    """Decorator: require a valid session (browser) or API key (Bearer header).

    Sets g.current_user with the user dict.
    """
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        # Already authenticated by before_request
        if hasattr(g, "current_user") and g.current_user:
            return f(*args, **kwargs)
        return jsonify({"error": "Não autenticado"}), 401
    return wrapper


def require_permission(permission: str):
    """Decorator: require a specific permission for the current user."""
    def decorator(f):
        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            user = getattr(g, "current_user", None)
            # No users in DB (first-run / test mode): skip permission check
            storage = getattr(g, "_storage", None)
            if storage and not storage.has_users():
                return f(*args, **kwargs)
            if not user:
                return jsonify({"error": "Não autenticado"}), 401
            # Admin always has all permissions
            if user["role"] == "admin":
                return f(*args, **kwargs)
            if storage and has_permission(storage, user["role"], permission):
                return f(*args, **kwargs)
            return jsonify({"error": "Sem permissão", "required": permission}), 403
        return wrapper
    return decorator


def setup_auth(app, storage):
    """Wire up auth into the Flask app: before_request hook + login routes."""
    global _rate_limiter
    from . import config as cfg
    _rate_limiter = LoginRateLimiter(
        max_attempts=cfg.MAX_LOGIN_ATTEMPTS,
        lockout_seconds=cfg.LOCKOUT_MINUTES * 60,
    )

    @app.before_request
    def check_authentication():
        """Authenticate every request. Skip public endpoints."""
        # Public: health, login, setup, static
        public_endpoints = {"health", "login_page", "login_post", "setup_page", "setup_post", "static"}
        if request.endpoint in public_endpoints:
            return
        # Always make storage available to decorators
        g._storage = storage
        # No users in DB yet (first-run / test mode): skip auth entirely
        if not storage.has_users():
            return

        g.current_user = None
        g.auth_method = None

        # 1. Try session cookie
        token = request.cookies.get("session_token")
        if token:
            user = validate_session(storage, token)
            if user:
                g.current_user = user
                g.auth_method = "session"
                g._storage = storage
                return

        # 2. Try API key (Bearer header)
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            api_key_token = auth_header[7:]
            import hashlib as _hl
            key_hash = _hl.sha256(api_key_token.encode()).hexdigest()
            api_key = storage.get_api_key_by_hash(key_hash)
            if api_key:
                storage.update_api_key_last_used(api_key["id"])
                # Create a virtual user from the API key
                g.current_user = {
                    "id": None,
                    "username": f"api:{api_key['name']}",
                    "role": "_api_key",
                    "_api_key": api_key,
                }
                g.auth_method = "api_key"
                g._storage = storage
                return

        # 3. Not authenticated
        # API requests get a JSON 401 so the SPA (fetchData) can redirect to
        # /login. Page navigations get redirected straight to the login page
        # instead of rendering the raw JSON error in the browser.
        if request.path.startswith("/api/"):
            return jsonify({"error": "Não autenticado"}), 401
        from flask import redirect
        return redirect("/login")

    # ── Login routes ──

    @app.route("/login")
    def login_page():
        if storage.has_users():
            from flask import render_template
            return render_template("login.html")
        from flask import redirect
        return redirect("/setup")

    @app.route("/api/auth/login", methods=["POST"])
    def login_post():
        from flask import make_response
        data = request.get_json(silent=True) or {}
        username = data.get("username", "").strip()
        password = data.get("password", "")

        if not username or not password:
            return jsonify({"error": "Usuário e senha são obrigatórios"}), 400

        # Rate limit check
        ip = request.remote_addr
        if _rate_limiter.is_locked(ip):
            return jsonify({"error": "Muitas tentativas. Tente novamente em 5 minutos."}), 429

        user = storage.get_user_by_username(username)
        if not user or not verify_password(password, user["password_hash"]):
            _rate_limiter.record_failure(ip)
            return jsonify({"error": "Credenciais inválidas"}), 401

        if not user.get("active"):
            return jsonify({"error": "Conta desativada"}), 403

        _rate_limiter.record_success(ip)

        # Create session
        token = create_session(storage, user["id"], request.remote_addr)
        storage.update_user(user["id"], last_login=datetime.now(timezone.utc).isoformat())
        storage.add_audit_entry("login", user_id=user["id"], ip_address=request.remote_addr)

        resp = make_response(jsonify({
            "status": "ok",
            "user": {
                "id": user["id"],
                "username": user["username"],
                "role": user["role"],
            },
        }))
        resp.set_cookie("session_token", token, httponly=True, samesite="Strict", path="/")
        return resp

    @app.route("/api/auth/logout", methods=["POST"])
    def logout_post():
        token = request.cookies.get("session_token")
        if token:
            storage.delete_session(token)
        from flask import make_response
        resp = make_response(jsonify({"status": "ok"}))
        resp.delete_cookie("session_token", path="/")
        return resp

    @app.route("/api/auth/me")
    @require_auth
    def auth_me():
        user = g.current_user
        if g.auth_method == "api_key":
            api_key = user.get("_api_key", {})
            return jsonify({
                "type": "api_key",
                "name": api_key.get("name"),
                "permissions": api_key.get("permissions"),
            })
        # Load permissions for browser session
        perms = {}
        storage_obj = getattr(g, "_storage", None)
        if storage_obj:
            role_perms = _permission_cache.get(storage_obj, user["role"])
            perms = {k: v for k, v in role_perms.items() if v}
        return jsonify({
            "type": "session",
            "user": {
                "id": user["id"],
                "username": user["username"],
                "role": user["role"],
            },
            "permissions": perms,
        })

    # ── First-run setup ──

    @app.route("/setup")
    def setup_page():
        if storage.has_users():
            from flask import abort
            abort(403)
        from flask import render_template
        return render_template("setup.html")

    @app.route("/api/setup", methods=["POST"])
    def setup_post():
        if storage.has_users():
            return jsonify({"error": "Sistema já configurado"}), 403

        data = request.get_json(silent=True) or {}
        username = data.get("username", "").strip()
        password = data.get("password", "")

        if not username or not password:
            return jsonify({"error": "Usuário e senha são obrigatórios"}), 400
        if len(password) < 6:
            return jsonify({"error": "Senha deve ter pelo menos 6 caracteres"}), 400

        pw_hash = hash_password(password)
        user_id = storage.add_user(username, pw_hash, "admin")
        storage.seed_default_permissions(DEFAULT_ROLE_PERMISSIONS)

        token = create_session(storage, user_id, request.remote_addr)
        storage.add_audit_entry("setup_create_admin", user_id=user_id, ip_address=request.remote_addr)

        from flask import make_response, redirect
        resp = make_response(redirect("/"))
        resp.set_cookie("session_token", token, httponly=True, samesite="Strict", path="/")
        return resp
