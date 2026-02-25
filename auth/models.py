"""
User data model with JSON file storage.

Users stored in /data/users.json (mounted Docker volume).
Passwords hashed with bcrypt. Never stored in plaintext.
"""

import json
import os
import uuid
from datetime import datetime, timezone

import bcrypt

from config import USERS_FILE


def _load_users() -> list[dict]:
    """Load users from JSON file."""
    if not os.path.exists(USERS_FILE):
        return []
    try:
        with open(USERS_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return []


def _save_users(users: list[dict]):
    """Save users to JSON file."""
    os.makedirs(os.path.dirname(USERS_FILE), exist_ok=True)
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=2, default=str)


def hash_password(password: str) -> str:
    """Hash a password with bcrypt."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against its bcrypt hash."""
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def get_all_users() -> list[dict]:
    """Return all users (without password hashes)."""
    users = _load_users()
    return [{k: v for k, v in u.items() if k != "password_hash"} for u in users]


def get_user_by_username(username: str) -> dict | None:
    """Find user by username."""
    users = _load_users()
    for u in users:
        if u["username"] == username:
            return u
    return None


def get_user_by_id(user_id: str) -> dict | None:
    """Find user by ID."""
    users = _load_users()
    for u in users:
        if u["id"] == user_id:
            return u
    return None


def create_user(username: str, password: str, display_name: str = "",
                role: str = "viewer") -> dict:
    """Create a new user. Returns the user dict (without password_hash)."""
    users = _load_users()

    # Check for duplicate username
    for u in users:
        if u["username"] == username:
            raise ValueError(f"Username '{username}' already exists")

    user = {
        "id": str(uuid.uuid4()),
        "username": username,
        "password_hash": hash_password(password),
        "display_name": display_name or username,
        "role": role,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "last_login": None,
        "active": True,
    }
    users.append(user)
    _save_users(users)

    return {k: v for k, v in user.items() if k != "password_hash"}


def update_user(user_id: str, **kwargs) -> dict | None:
    """Update user fields. Returns updated user or None if not found."""
    users = _load_users()
    for i, u in enumerate(users):
        if u["id"] == user_id:
            if "password" in kwargs:
                u["password_hash"] = hash_password(kwargs.pop("password"))
            for key in ("display_name", "role", "active"):
                if key in kwargs:
                    u[key] = kwargs[key]
            users[i] = u
            _save_users(users)
            return {k: v for k, v in u.items() if k != "password_hash"}
    return None


def delete_user(user_id: str) -> bool:
    """Delete a user. Returns True if deleted, False if not found."""
    users = _load_users()
    new_users = [u for u in users if u["id"] != user_id]
    if len(new_users) == len(users):
        return False
    _save_users(new_users)
    return True


def update_last_login(username: str):
    """Update user's last_login timestamp."""
    users = _load_users()
    for u in users:
        if u["username"] == username:
            u["last_login"] = datetime.now(timezone.utc).isoformat()
            _save_users(users)
            return


def authenticate(username: str, password: str) -> dict | None:
    """Validate credentials. Returns user dict (no hash) or None."""
    user = get_user_by_username(username)
    if not user:
        return None
    if not user.get("active", True):
        return None
    if not verify_password(password, user["password_hash"]):
        return None
    update_last_login(username)
    return {k: v for k, v in user.items() if k != "password_hash"}


def user_count() -> int:
    """Return the total number of users."""
    return len(_load_users())
