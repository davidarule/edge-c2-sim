"""
Auth configuration — loaded from environment variables.
"""

import os


JWT_SECRET = os.environ.get("JWT_SECRET", "dev-secret-change-in-production")
JWT_ALGORITHM = os.environ.get("JWT_ALGORITHM", "HS256")
JWT_EXPIRY_HOURS = int(os.environ.get("JWT_EXPIRY_HOURS", "24"))

COOKIE_NAME = os.environ.get("COOKIE_NAME", "edge_c2_session")
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "false").lower() == "true"
COOKIE_DOMAIN = os.environ.get("COOKIE_DOMAIN", None)  # None = current domain

USERS_FILE = os.environ.get("USERS_FILE", "/data/users.json")

ADMIN_BOOTSTRAP = os.environ.get("ADMIN_BOOTSTRAP", "true").lower() == "true"
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
