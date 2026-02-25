"""
Authentication service for Edge C2 Simulator.

Provides:
- Login page (HTML form)
- JWT token issuance on successful login
- Token validation endpoint (for Nginx auth_request)
- User management API (add/remove/list users)
- Password hashing with bcrypt

Users are stored in a JSON file mounted as a Docker volume
so they persist across container restarts.
"""

import logging
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, Request, Response, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from jose import jwt, JWTError
from pydantic import BaseModel

import config
import models

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("auth")

app = FastAPI(title="Edge C2 Auth Service", docs_url=None, redoc_url=None)
templates = Jinja2Templates(directory="templates")


# ── Startup: bootstrap admin user ──

@app.on_event("startup")
async def startup():
    if config.ADMIN_BOOTSTRAP and models.user_count() == 0:
        if not config.ADMIN_PASSWORD:
            logger.warning(
                "ADMIN_BOOTSTRAP=true but ADMIN_PASSWORD not set. "
                "Using default password 'admin'. CHANGE THIS IN PRODUCTION."
            )
            password = "admin"
        else:
            password = config.ADMIN_PASSWORD
        models.create_user(
            username=config.ADMIN_USERNAME,
            password=password,
            display_name="Administrator",
            role="admin",
        )
        logger.info(f"Bootstrap admin user '{config.ADMIN_USERNAME}' created.")


# ── JWT helpers ──

def create_token(user: dict) -> str:
    """Create a JWT token for the given user."""
    expire = datetime.now(timezone.utc) + timedelta(hours=config.JWT_EXPIRY_HOURS)
    payload = {
        "sub": user["username"],
        "uid": user["id"],
        "role": user.get("role", "viewer"),
        "name": user.get("display_name", user["username"]),
        "exp": expire,
    }
    return jwt.encode(payload, config.JWT_SECRET, algorithm=config.JWT_ALGORITHM)


def decode_token(token: str) -> dict | None:
    """Decode and validate a JWT token. Returns payload or None."""
    try:
        payload = jwt.decode(
            token, config.JWT_SECRET, algorithms=[config.JWT_ALGORITHM]
        )
        return payload
    except JWTError:
        return None


def get_token_from_request(request: Request) -> str | None:
    """Extract JWT from cookie or Authorization header."""
    # Try cookie first
    token = request.cookies.get(config.COOKIE_NAME)
    if token:
        return token
    # Try Authorization header
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return None


def set_auth_cookie(response: Response, token: str):
    """Set the JWT auth cookie on a response."""
    response.set_cookie(
        key=config.COOKIE_NAME,
        value=token,
        httponly=True,
        secure=config.COOKIE_SECURE,
        samesite="lax",
        domain=config.COOKIE_DOMAIN,
        max_age=config.JWT_EXPIRY_HOURS * 3600,
        path="/",
    )


def clear_auth_cookie(response: Response):
    """Clear the JWT auth cookie."""
    response.delete_cookie(
        key=config.COOKIE_NAME,
        domain=config.COOKIE_DOMAIN,
        path="/",
    )


def require_admin(request: Request) -> dict:
    """Dependency: require a valid admin JWT."""
    token = get_token_from_request(request)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    if payload.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return payload


# ── Routes ──

@app.get("/auth/login", response_class=HTMLResponse)
async def login_page(request: Request, next: str = "/", error: str = ""):
    """Serve the login page."""
    # If already authenticated, redirect to the app
    token = get_token_from_request(request)
    if token and decode_token(token):
        return RedirectResponse(url=next, status_code=302)
    return templates.TemplateResponse("login.html", {
        "request": request,
        "error": error,
        "next": next,
    })


@app.post("/auth/login")
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    next: str = Form("/"),
):
    """Validate credentials, set JWT cookie, redirect."""
    user = models.authenticate(username, password)
    if not user:
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": "Invalid username or password",
            "next": next,
        }, status_code=401)

    token = create_token(user)
    redirect_to = next if next and next != "/auth/login" else "/"
    response = RedirectResponse(url=redirect_to, status_code=302)
    set_auth_cookie(response, token)
    logger.info(f"User '{username}' logged in successfully")
    return response


@app.post("/auth/logout")
async def logout():
    """Clear JWT cookie, redirect to login."""
    response = RedirectResponse(url="/auth/login", status_code=302)
    clear_auth_cookie(response)
    return response


@app.get("/auth/logout")
async def logout_get():
    """Also allow GET logout for convenience."""
    response = RedirectResponse(url="/auth/login", status_code=302)
    clear_auth_cookie(response)
    return response


@app.get("/auth/validate")
async def validate(request: Request):
    """
    Called by Nginx auth_request on every protected request.
    Returns 200 if valid JWT cookie present, 401 otherwise.
    """
    token = get_token_from_request(request)
    if not token:
        return Response(status_code=401)
    payload = decode_token(token)
    if not payload:
        return Response(status_code=401)
    return Response(status_code=200)


@app.get("/auth/me")
async def me(request: Request):
    """Return current user info from JWT."""
    token = get_token_from_request(request)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    return {
        "username": payload.get("sub"),
        "id": payload.get("uid"),
        "role": payload.get("role"),
        "display_name": payload.get("name"),
    }


# ── User Management API (admin only) ──

class UserCreate(BaseModel):
    username: str
    password: str
    display_name: str = ""
    role: str = "viewer"


class UserUpdate(BaseModel):
    password: str | None = None
    display_name: str | None = None
    role: str | None = None
    active: bool | None = None


@app.get("/auth/api/users")
async def list_users(admin: dict = Depends(require_admin)):
    """List all users."""
    return models.get_all_users()


@app.post("/auth/api/users", status_code=201)
async def create_user(data: UserCreate, admin: dict = Depends(require_admin)):
    """Create a new user."""
    try:
        user = models.create_user(
            username=data.username,
            password=data.password,
            display_name=data.display_name,
            role=data.role,
        )
        return user
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@app.put("/auth/api/users/{user_id}")
async def update_user(
    user_id: str, data: UserUpdate, admin: dict = Depends(require_admin)
):
    """Update a user's fields."""
    update_fields = {k: v for k, v in data.model_dump().items() if v is not None}
    if not update_fields:
        raise HTTPException(status_code=400, detail="No fields to update")
    user = models.update_user(user_id, **update_fields)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@app.delete("/auth/api/users/{user_id}")
async def delete_user(user_id: str, admin: dict = Depends(require_admin)):
    """Delete a user."""
    if not models.delete_user(user_id):
        raise HTTPException(status_code=404, detail="User not found")
    return {"ok": True}


# ── Health ──

@app.get("/auth/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "service": "auth", "users": models.user_count()}
