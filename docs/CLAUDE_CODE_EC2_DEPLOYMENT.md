# Claude Code — EC2 Deployment with Authentication

## Context

The Edge C2 Simulator needs to be deployed to an AWS EC2 instance at
`ec2sim.brumbiesoft.org` so that it can be accessed remotely for review
and demonstration. DNS is managed via Cloudflare. The deployment needs
authentication to prevent unauthorized access to the simulation.

**Current architecture:**
- `simulator` container: Python, ports 8765 (WebSocket) + 8766 (health)
- `cop` container: Nginx serving static Vite build, port 3000
- `docker-compose.yml` ties them together

**Target architecture:**
- Cloudflare DNS → EC2 public IP
- Cloudflare handles SSL (edge certificates)
- Nginx reverse proxy on EC2 as single entry point (port 443)
- Auth service for login/session management
- All internal services on Docker network (no public ports except 80/443)

```
Internet
   │
   ▼
Cloudflare (DNS + SSL + CDN + WAF)
   │  HTTPS
   ▼
EC2 Instance
   │
   ▼
┌─────────────────────────────────────────────────────┐
│  Nginx Reverse Proxy (:80, :443)                     │
│  ┌─────────────────────────────────────────────────┐ │
│  │ /auth/*    → auth-service:8080                  │ │
│  │ /ws        → simulator:8765 (WebSocket upgrade) │ │
│  │ /health    → simulator:8766                     │ │
│  │ /*         → cop:3000 (static files)            │ │
│  │                                                  │ │
│  │ ALL routes except /auth/login require valid JWT  │ │
│  └─────────────────────────────────────────────────┘ │
│                                                      │
│  Docker Network: edge_c2_net                         │
│  ┌──────────┐ ┌─────┐ ┌──────┐ ┌──────────────────┐ │
│  │simulator │ │ cop │ │nginx │ │  auth-service     │ │
│  │ :8765    │ │:3000│ │:80   │ │  :8080            │ │
│  │ :8766    │ │     │ │:443  │ │  (login, users,   │ │
│  └──────────┘ └─────┘ └──────┘ │   session mgmt)   │ │
│                                 └──────────────────┘ │
└─────────────────────────────────────────────────────┘
```

---

## Task 1: Auth Service

### 1a. Create the auth service

Create `auth/` directory in the project root with a small FastAPI application.

**Why FastAPI:** Lightweight, async, Python (matches the simulator stack),
has good JWT support, and we can add it as another Docker container with
minimal overhead.

Create `auth/main.py`:

```python
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

# FastAPI application
# Endpoints:
#
# GET  /auth/login          → Serve login page HTML
# POST /auth/login          → Validate credentials, set JWT cookie, redirect to /
# POST /auth/logout         → Clear JWT cookie, redirect to /auth/login
# GET  /auth/validate       → Called by Nginx auth_request. Returns 200 if
#                              valid JWT cookie present, 401 otherwise.
#                              This is the critical endpoint — Nginx calls
#                              this on EVERY request to protected routes.
# GET  /auth/me             → Return current user info from JWT
#
# --- User Management (requires admin role) ---
# GET  /auth/api/users      → List all users
# POST /auth/api/users      → Create new user
# PUT  /auth/api/users/{id} → Update user (password, role)
# DELETE /auth/api/users/{id} → Delete user
#
# --- Health ---
# GET  /auth/health         → Returns 200 OK
```

### 1b. User Model

Create `auth/models.py`:

```python
"""
User data model.

Users are stored in /data/users.json (mounted Docker volume).
Passwords are hashed with bcrypt. Never store plaintext passwords.

User schema:
{
  "id": "uuid",
  "username": "david",
  "password_hash": "$2b$12$...",    # bcrypt hash
  "display_name": "David",
  "role": "admin",                   # "admin" or "viewer"
  "created_at": "2026-02-26T...",
  "last_login": "2026-02-26T...",
  "active": true
}

Roles:
  admin  — Can manage users, change scenarios, full access
  viewer — Can view the COP, cannot manage users
"""
```

### 1c. JWT Configuration

Create `auth/config.py`:

```python
"""
Auth configuration — loaded from environment variables.

JWT_SECRET       — Secret key for signing JWTs. MUST be set in production.
                   Generate with: python -c "import secrets; print(secrets.token_hex(32))"
JWT_ALGORITHM    — "HS256" (default)
JWT_EXPIRY_HOURS — Token lifetime in hours (default: 24)
COOKIE_NAME      — Name of the auth cookie (default: "edge_c2_session")
COOKIE_SECURE    — Set Secure flag on cookie (default: true for production)
COOKIE_DOMAIN    — Cookie domain (default: ".brumbiesoft.org")
USERS_FILE       — Path to users JSON file (default: "/data/users.json")
ADMIN_BOOTSTRAP  — If "true" and no users exist, create admin user on startup
ADMIN_USERNAME   — Bootstrap admin username (default: "admin")
ADMIN_PASSWORD   — Bootstrap admin password (MUST be set if ADMIN_BOOTSTRAP=true)
"""
```

### 1d. Login Page

Create `auth/templates/login.html`:

A simple, professional login page that matches the COP dark theme:

```
┌──────────────────────────────────────────────┐
│                                              │
│            ┌──────────────────┐              │
│            │                  │              │
│            │   Edge C2        │              │
│            │   Simulator      │              │
│            │                  │              │
│            │  ┌────────────┐  │              │
│            │  │ Username   │  │              │
│            │  └────────────┘  │              │
│            │  ┌────────────┐  │              │
│            │  │ Password   │  │              │
│            │  └────────────┘  │              │
│            │                  │              │
│            │  [  Sign In  ]   │              │
│            │                  │              │
│            │  Invalid creds   │  ◄── error   │
│            │  shown here      │     message  │
│            │                  │              │
│            └──────────────────┘              │
│                                              │
│  Background: #0D1117                         │
│  Card: #161B22 with #30363D border           │
│  Accent: #58A6FF                             │
│  Font: IBM Plex Sans                         │
└──────────────────────────────────────────────┘
```

Style the login page with the SAME dark theme as the COP dashboard:
- Background: `#0D1117`
- Card surface: `#161B22`
- Border: `#30363D`
- Text: `#C9D1D9`
- Button: `#58A6FF` background, white text
- Error: `#F85149`
- Font: IBM Plex Sans from Google Fonts
- Centered vertically and horizontally
- Responsive for mobile

### 1e. Auth Service Dockerfile

Create `auth/Dockerfile`:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8080

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
```

Create `auth/requirements.txt`:

```
fastapi==0.109.0
uvicorn==0.27.0
python-jose[cryptography]==3.3.0
bcrypt==4.1.2
python-multipart==0.0.6
jinja2==3.1.3
```

### 1f. WebSocket Authentication

The WebSocket connection needs auth too. Two approaches — use BOTH:

**Approach 1: Cookie-based (primary)**
The browser sends the JWT cookie automatically with the WebSocket
upgrade request. Nginx forwards the cookie. The simulator's WebSocket
handler validates it.

Add to the simulator's WebSocket adapter (`simulator/transport/websocket_adapter.py`):

```python
"""
WebSocket authentication:

On connection upgrade, check for the JWT cookie in the request headers.
If valid → accept connection.
If missing/invalid → reject with 401.

The JWT_SECRET must match the auth service's secret (shared via
environment variable).

For development (localhost), auth can be disabled with WS_AUTH=false
environment variable.
"""
```

**Approach 2: Token in URL (fallback)**
For tools/scripts that can't send cookies (e.g., testing with wscat):
`wss://ec2sim.brumbiesoft.org/ws?token=<jwt_token>`

Nginx passes the query param through. The WebSocket handler checks it.

---

## Task 2: Nginx Reverse Proxy

### 2a. Nginx Configuration

Create `nginx/nginx.conf`:

```nginx
# Edge C2 Simulator — Reverse Proxy Configuration
#
# This Nginx instance is the ONLY entry point to the application.
# It handles:
#   1. SSL termination (with Cloudflare origin certificate)
#   2. Authentication via auth_request to the auth service
#   3. Routing to COP, WebSocket, health check, and auth service
#   4. Security headers
#   5. Rate limiting

# Rate limiting zones
limit_req_zone $binary_remote_addr zone=login:10m rate=5r/m;
limit_req_zone $binary_remote_addr zone=api:10m rate=30r/s;

# WebSocket upgrade map
map $http_upgrade $connection_upgrade {
    default upgrade;
    ''      close;
}

server {
    listen 80;
    server_name ec2sim.brumbiesoft.org;
    # Redirect all HTTP to HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl;
    server_name ec2sim.brumbiesoft.org;

    # --- SSL (Cloudflare Origin Certificate) ---
    ssl_certificate     /etc/nginx/ssl/origin.pem;
    ssl_certificate_key /etc/nginx/ssl/origin-key.pem;
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         HIGH:!aNULL:!MD5;

    # --- Security Headers ---
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cesium.com https://cdn.cesium.com https://assets.cesium.com; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' data: blob: https://*.cesium.com https://*.arcgisonline.com https://*.mapbox.com; connect-src 'self' wss://ec2sim.brumbiesoft.org https://*.cesium.com https://assets.cesium.com; worker-src 'self' blob:;" always;

    # --- Auth Service (NO auth_request on these) ---
    location /auth/ {
        # Rate limit login attempts
        limit_req zone=login burst=3 nodelay;

        proxy_pass http://auth-service:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # --- Internal auth validation endpoint ---
    # Nginx calls this on every protected request.
    # Returns 200 → allow, 401 → redirect to login.
    location = /auth/validate {
        internal;
        proxy_pass http://auth-service:8080/auth/validate;
        proxy_pass_request_body off;
        proxy_set_header Content-Length "";
        proxy_set_header X-Original-URI $request_uri;
        proxy_set_header Cookie $http_cookie;
    }

    # --- WebSocket (Simulator) ---
    location /ws {
        auth_request /auth/validate;
        error_page 401 = @login_redirect;

        proxy_pass http://simulator:8765;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Cookie $http_cookie;

        # WebSocket timeouts
        proxy_read_timeout 86400;   # 24 hours — keep WS alive
        proxy_send_timeout 86400;
    }

    # --- Health Check (public, no auth) ---
    location /health {
        proxy_pass http://simulator:8766/health;
        proxy_set_header Host $host;
    }

    # --- COP Dashboard (protected) ---
    location / {
        auth_request /auth/validate;
        error_page 401 = @login_redirect;

        proxy_pass http://cop:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # --- Login redirect handler ---
    location @login_redirect {
        return 302 /auth/login?next=$request_uri;
    }

    # --- Block sensitive paths ---
    location ~ /\. {
        deny all;
    }
}
```

### 2b. Nginx Dockerfile

Create `nginx/Dockerfile`:

```dockerfile
FROM nginx:alpine

# Remove default config
RUN rm /etc/nginx/conf.d/default.conf

# Copy our config
COPY nginx.conf /etc/nginx/conf.d/edge_c2.conf

# SSL directory (certs mounted at runtime)
RUN mkdir -p /etc/nginx/ssl

EXPOSE 80 443
```

### 2c. Important: COP WebSocket URL Change

The COP frontend currently connects to WebSocket using a hardcoded or
env-based URL like `ws://localhost:8765`. For production, it needs to
connect through the Nginx proxy:

Update `cop/src/config.js` (or wherever WS URL is configured):

```javascript
/**
 * Determine WebSocket URL based on current page location.
 *
 * In production (served through Nginx proxy):
 *   wss://ec2sim.brumbiesoft.org/ws
 *
 * In development (direct connection):
 *   ws://localhost:8765
 *
 * Logic: if page is served over HTTPS, use wss:// through /ws path.
 *        if page is served over HTTP (localhost), use direct WS URL.
 */
function getWebSocketUrl() {
    if (window.location.protocol === 'https:') {
        return `wss://${window.location.host}/ws`;
    }
    // Fall back to env variable or default for dev
    return import.meta.env.VITE_WS_URL || 'ws://localhost:8765';
}
```

Also update the WebSocket adapter in the simulator to accept connections
on the `/ws` path (Nginx strips nothing here — it proxies to the
simulator's root WebSocket). The simulator's WebSocket server should
accept connections regardless of the URL path.

---

## Task 3: Updated Docker Compose for Production

### 3a. Production docker-compose

Create `docker-compose.prod.yml`:

```yaml
version: '3.8'

services:
  # --- Nginx Reverse Proxy ---
  nginx:
    build: ./nginx
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/ssl:/etc/nginx/ssl:ro   # Cloudflare origin certs
    depends_on:
      - cop
      - simulator
      - auth-service
    networks:
      - edge_c2_net
    restart: unless-stopped

  # --- Auth Service ---
  auth-service:
    build: ./auth
    environment:
      - JWT_SECRET=${JWT_SECRET}
      - JWT_EXPIRY_HOURS=${JWT_EXPIRY_HOURS:-24}
      - COOKIE_DOMAIN=${COOKIE_DOMAIN:-.brumbiesoft.org}
      - COOKIE_SECURE=true
      - ADMIN_BOOTSTRAP=true
      - ADMIN_USERNAME=${ADMIN_USERNAME:-admin}
      - ADMIN_PASSWORD=${ADMIN_PASSWORD}
    volumes:
      - auth_data:/data    # Persistent user database
    networks:
      - edge_c2_net
    restart: unless-stopped

  # --- Simulator ---
  simulator:
    build:
      context: .
      dockerfile: Dockerfile
    environment:
      - SCENARIO=${SCENARIO:-config/scenarios/demo_combined.yaml}
      - SIM_SPEED=${SIM_SPEED:-1}
      - JWT_SECRET=${JWT_SECRET}
      - WS_AUTH=${WS_AUTH:-true}
    volumes:
      - ./config:/app/config
      - ./geodata:/app/geodata
      - ./logs:/app/logs
    command: >
      edge-c2-sim
        --scenario ${SCENARIO:-config/scenarios/demo_combined.yaml}
        --speed ${SIM_SPEED:-1}
        --transport ws,console
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8766/health"]
      interval: 10s
      timeout: 5s
      retries: 3
    networks:
      - edge_c2_net
    restart: unless-stopped

  # --- COP Dashboard ---
  cop:
    build:
      context: ./cop
      args:
        - VITE_CESIUM_ION_TOKEN=${CESIUM_ION_TOKEN}
        - VITE_WS_URL=wss://ec2sim.brumbiesoft.org/ws
    networks:
      - edge_c2_net
    restart: unless-stopped

networks:
  edge_c2_net:
    driver: bridge

volumes:
  auth_data:
```

**Key differences from dev docker-compose:**
- No ports exposed on simulator/cop/auth (only Nginx exposes 80/443)
- All services on a shared Docker network
- Auth service added
- Nginx added as reverse proxy
- SSL volume for Cloudflare origin certs
- `restart: unless-stopped` on all services
- JWT_SECRET shared between auth service and simulator

### 3b. Production Environment File

Create `.env.production.example`:

```bash
# Edge C2 Simulator — Production Environment
# Copy to .env and fill in all values before deploying.

# --- REQUIRED ---

# Cesium Ion token (get from https://cesium.com/ion/tokens)
CESIUM_ION_TOKEN=your_cesium_ion_token_here

# JWT secret for signing auth tokens
# Generate with: python3 -c "import secrets; print(secrets.token_hex(32))"
JWT_SECRET=CHANGE_ME_TO_A_RANDOM_64_CHAR_HEX_STRING

# Initial admin password (used on first startup only)
ADMIN_PASSWORD=CHANGE_ME_TO_A_STRONG_PASSWORD

# --- OPTIONAL ---

# Admin username (default: admin)
ADMIN_USERNAME=admin

# JWT token lifetime in hours (default: 24)
JWT_EXPIRY_HOURS=24

# Cookie domain (default: .brumbiesoft.org)
COOKIE_DOMAIN=.brumbiesoft.org

# Scenario to run (default: demo_combined.yaml)
SCENARIO=config/scenarios/demo_combined.yaml

# Simulation speed multiplier (default: 1)
SIM_SPEED=1

# WebSocket authentication (default: true, set false for local dev)
WS_AUTH=true
```

---

## Task 4: EC2 Instance Setup Script

### 4a. Server provisioning script

Create `scripts/ec2-setup.sh`:

```bash
#!/bin/bash
# EC2 Instance Setup Script for Edge C2 Simulator
#
# Run this on a fresh Ubuntu 24.04 EC2 instance.
# Tested on: t3.small (2 vCPU, 2GB RAM) — minimum for dev/review (swap required)
# Recommended for production: t3.medium+ (2 vCPU, 4GB RAM)
# Note: Docker builds (especially COP/CesiumJS) are RAM-hungry.
#       The swap file created below prevents OOM kills on t3.small.
#
# Usage:
#   1. SSH into your EC2 instance
#   2. Copy this script: scp scripts/ec2-setup.sh ubuntu@<ec2-ip>:~/
#   3. Run: chmod +x ec2-setup.sh && sudo ./ec2-setup.sh
#
# What this does:
#   - Updates system packages
#   - Installs Docker and Docker Compose
#   - Installs security tools (fail2ban, ufw)
#   - Configures firewall (only 22, 80, 443 open)
#   - Creates deploy user and directory structure
#   - Sets up log rotation
#   - Configures unattended security updates

set -euo pipefail

echo "╔══════════════════════════════════════════════╗"
echo "║  Edge C2 Simulator — EC2 Setup               ║"
echo "╚══════════════════════════════════════════════╝"

# --- System Update ---
echo "[1/8] Updating system packages..."
apt-get update -y
apt-get upgrade -y
apt-get install -y \
    apt-transport-https \
    ca-certificates \
    curl \
    gnupg \
    lsb-release \
    git \
    unzip \
    htop \
    jq

# --- Swap File (essential for t3.small with 2GB RAM) ---
echo "[2/9] Creating 2GB swap file..."
if [ ! -f /swapfile ]; then
    fallocate -l 2G /swapfile
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    echo '/swapfile none swap sw 0 0' >> /etc/fstab
    echo "Swap enabled: $(swapon --show)"
else
    echo "Swap file already exists, skipping."
fi

# --- Docker Installation ---
echo "[3/9] Installing Docker..."
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh
rm get-docker.sh

# Install Docker Compose plugin
apt-get install -y docker-compose-plugin

# Enable Docker to start on boot
systemctl enable docker
systemctl start docker

# --- Create deploy user ---
echo "[4/9] Creating deploy user..."
if ! id "deploy" &>/dev/null; then
    useradd -m -s /bin/bash -G docker deploy
    mkdir -p /home/deploy/.ssh
    # Copy authorized_keys from ubuntu user so same SSH key works
    cp /home/ubuntu/.ssh/authorized_keys /home/deploy/.ssh/
    chown -R deploy:deploy /home/deploy/.ssh
    chmod 700 /home/deploy/.ssh
    chmod 600 /home/deploy/.ssh/authorized_keys
    echo "deploy ALL=(ALL) NOPASSWD: /usr/bin/docker, /usr/bin/docker compose" > /etc/sudoers.d/deploy
fi

# --- Application directory ---
echo "[5/9] Setting up application directory..."
mkdir -p /opt/edge-c2-sim
chown deploy:deploy /opt/edge-c2-sim

# --- Firewall (UFW) ---
echo "[6/9] Configuring firewall..."
apt-get install -y ufw
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp    comment 'SSH'
ufw allow 80/tcp    comment 'HTTP (redirect to HTTPS)'
ufw allow 443/tcp   comment 'HTTPS'
ufw --force enable
echo "Firewall rules:"
ufw status verbose

# --- Fail2Ban ---
echo "[7/9] Installing fail2ban..."
apt-get install -y fail2ban
cat > /etc/fail2ban/jail.local << 'EOF'
[DEFAULT]
bantime  = 3600
findtime = 600
maxretry = 5

[sshd]
enabled = true
port    = ssh
filter  = sshd
logpath = /var/log/auth.log
maxretry = 3
bantime = 7200
EOF

systemctl enable fail2ban
systemctl restart fail2ban

# --- Log Rotation for Docker ---
echo "[8/9] Configuring Docker log rotation..."
cat > /etc/docker/daemon.json << 'EOF'
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  }
}
EOF
systemctl restart docker

# --- Unattended Security Updates ---
echo "[9/9] Enabling unattended security updates..."
apt-get install -y unattended-upgrades
cat > /etc/apt/apt.conf.d/20auto-upgrades << 'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
APT::Periodic::AutocleanInterval "7";
EOF

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║  Setup complete!                              ║"
echo "║                                               ║"
echo "║  Next steps:                                  ║"
echo "║  1. Clone your repo to /opt/edge-c2-sim       ║"
echo "║  2. Copy .env.production → .env and fill in   ║"
echo "║  3. Add Cloudflare origin cert to nginx/ssl/   ║"
echo "║  4. Run: docker compose -f                    ║"
echo "║     docker-compose.prod.yml up -d --build     ║"
echo "╚══════════════════════════════════════════════╝"
```

### 4b. AWS Security Group

The EC2 instance's AWS Security Group should allow:

| Type  | Port | Source          | Description           |
|-------|------|----------------|-----------------------|
| SSH   | 22   | Your IP only   | SSH access            |
| HTTP  | 80   | 0.0.0.0/0      | Redirect to HTTPS     |
| HTTPS | 443  | 0.0.0.0/0      | Main application      |

**IMPORTANT:** Restrict SSH to your IP address or a small CIDR range.
Do NOT leave SSH open to 0.0.0.0/0.

If you want to be extra cautious, restrict HTTP/HTTPS to Cloudflare IP
ranges only. Cloudflare publishes their IP ranges at:
https://www.cloudflare.com/ips/

---

## Task 5: Cloudflare Origin Certificate

### 5a. Generate Origin Certificate

The human (David) will do this in Cloudflare dashboard:

```
1. Log in to Cloudflare → select brumbiesoft.org
2. SSL/TLS → Origin Server → Create Certificate
3. Settings:
   - Generate private key and CSR with Cloudflare
   - Hostnames: ec2sim.brumbiesoft.org
   - Certificate Validity: 15 years (default)
4. Save the PEM certificate as: nginx/ssl/origin.pem
5. Save the PEM private key as: nginx/ssl/origin-key.pem
```

### 5b. SSL Directory Setup

Claude Code should create the directory structure and a .gitignore:

```
nginx/
├── nginx.conf
├── Dockerfile
└── ssl/
    ├── .gitignore     # Contains: *.pem
    ├── origin.pem     # Cloudflare origin cert (human adds)
    └── origin-key.pem # Cloudflare origin key (human adds)
```

**NEVER commit SSL certificates to git.** The `.gitignore` in `nginx/ssl/`
must contain `*.pem` and `*.key`.

### 5c. Cloudflare SSL Mode

The human should set Cloudflare SSL mode to **Full (strict)**:

```
Cloudflare Dashboard → SSL/TLS → Overview → Full (strict)
```

This means:
- Browser → Cloudflare: HTTPS (Cloudflare edge cert)
- Cloudflare → EC2: HTTPS (Cloudflare origin cert)
- End-to-end encrypted

---

## Task 6: Deployment Script

### 6a. Deploy script

Create `scripts/deploy.sh`:

```bash
#!/bin/bash
# Deploy Edge C2 Simulator to EC2
#
# Usage: ./scripts/deploy.sh
#
# Prerequisites:
#   1. EC2 instance set up with ec2-setup.sh
#   2. SSH access to deploy@<ec2-ip>
#   3. .env file configured on the server
#   4. Cloudflare origin certs in nginx/ssl/
#
# This script:
#   1. Builds Docker images locally (or on the server)
#   2. Pushes code to the server via rsync
#   3. Rebuilds and restarts containers on the server

set -euo pipefail

# Configuration — update these
EC2_HOST="${EC2_HOST:-deploy@ec2sim.brumbiesoft.org}"
DEPLOY_DIR="/opt/edge-c2-sim"
COMPOSE_FILE="docker-compose.prod.yml"

echo "╔══════════════════════════════════════════╗"
echo "║  Deploying Edge C2 Simulator              ║"
echo "╚══════════════════════════════════════════╝"

echo "[1/4] Syncing files to server..."
rsync -avz --delete \
    --exclude '.git' \
    --exclude 'node_modules' \
    --exclude '__pycache__' \
    --exclude '.env' \
    --exclude 'nginx/ssl/*.pem' \
    --exclude 'logs/' \
    --exclude '.pytest_cache' \
    --exclude 'cop/dist' \
    ./ "${EC2_HOST}:${DEPLOY_DIR}/"

echo "[2/4] Building containers on server..."
ssh "${EC2_HOST}" "cd ${DEPLOY_DIR} && sudo docker compose -f ${COMPOSE_FILE} build"

echo "[3/4] Restarting services..."
ssh "${EC2_HOST}" "cd ${DEPLOY_DIR} && sudo docker compose -f ${COMPOSE_FILE} down --timeout 10"
ssh "${EC2_HOST}" "cd ${DEPLOY_DIR} && sudo docker compose -f ${COMPOSE_FILE} up -d"

echo "[4/4] Checking health..."
sleep 10
ssh "${EC2_HOST}" "curl -sf http://localhost/health | jq ."

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║  Deployment complete!                     ║"
echo "║  https://ec2sim.brumbiesoft.org            ║"
echo "╚══════════════════════════════════════════╝"
```

### 6b. Quick commands reference

Create `scripts/server-commands.sh`:

```bash
#!/bin/bash
# Server management quick commands
# Source this file: source scripts/server-commands.sh
# Then run commands like: sim-logs, sim-restart, etc.

COMPOSE="sudo docker compose -f /opt/edge-c2-sim/docker-compose.prod.yml"
PROJECT_DIR="/opt/edge-c2-sim"

# View logs
alias sim-logs="cd $PROJECT_DIR && $COMPOSE logs -f"
alias sim-logs-sim="cd $PROJECT_DIR && $COMPOSE logs -f simulator"
alias sim-logs-cop="cd $PROJECT_DIR && $COMPOSE logs -f cop"
alias sim-logs-auth="cd $PROJECT_DIR && $COMPOSE logs -f auth-service"
alias sim-logs-nginx="cd $PROJECT_DIR && $COMPOSE logs -f nginx"

# Service management
alias sim-restart="cd $PROJECT_DIR && $COMPOSE restart"
alias sim-stop="cd $PROJECT_DIR && $COMPOSE down"
alias sim-start="cd $PROJECT_DIR && $COMPOSE up -d"
alias sim-rebuild="cd $PROJECT_DIR && $COMPOSE up -d --build"
alias sim-status="cd $PROJECT_DIR && $COMPOSE ps"

# Health check
alias sim-health="curl -sf http://localhost/health | jq ."

# User management (via auth service API)
sim-add-user() {
    local username=$1
    local password=$2
    local role=${3:-viewer}
    curl -sf -X POST http://localhost:8080/auth/api/users \
        -H "Content-Type: application/json" \
        -d "{\"username\":\"$username\",\"password\":\"$password\",\"role\":\"$role\"}" | jq .
}

sim-list-users() {
    curl -sf http://localhost:8080/auth/api/users | jq .
}

# Scenario management
sim-change-scenario() {
    local scenario=$1
    echo "Changing scenario to: $scenario"
    cd $PROJECT_DIR
    SCENARIO="$scenario" $COMPOSE up -d simulator
}
```

---

## Task 7: Security Hardening

### 7a. Secrets Management

**Rule: No secrets in code or Docker images.**

All secrets are in `.env` on the server, which is:
- NOT in git (`.gitignore` must include `.env`)
- Readable only by deploy user (`chmod 600 .env`)
- Contains: JWT_SECRET, ADMIN_PASSWORD, CESIUM_ION_TOKEN

### 7b. Docker Security

Add to each service in `docker-compose.prod.yml`:

```yaml
    # Run as non-root
    user: "1000:1000"
    # Read-only root filesystem where possible
    read_only: true
    tmpfs:
      - /tmp
    # Drop all capabilities, add only needed ones
    security_opt:
      - no-new-privileges:true
```

Note: The `user` directive may need adjustment per container. The Nginx
container needs specific capabilities. Apply `read_only` and `no-new-privileges`
where they don't break functionality. Test each service.

### 7c. Rate Limiting

Already configured in Nginx:
- Login endpoint: 5 requests/minute per IP (prevents brute force)
- API endpoints: 30 requests/second per IP
- Fail2ban on SSH: 3 failed attempts → 2 hour ban

### 7d. CORS

The COP is served from the same domain as the WebSocket, so CORS
is not needed. If you need cross-origin access later, configure it
explicitly in Nginx — do NOT use `Access-Control-Allow-Origin: *`.

### 7e. Content Security Policy

Already configured in the Nginx config above. The CSP allows:
- CesiumJS from cesium.com CDN
- Google Fonts
- WebSocket connections to the same origin
- Blob URLs (CesiumJS workers)
- Inline styles (CesiumJS needs them)

Test the CSP by checking the browser console for violations.

---

## Task 8: Monitoring & Observability

### 8a. Health Check Endpoint

The simulator already has `/health` on port 8766. Nginx proxies this
publicly at `/health` (no auth required) so external monitoring tools
can check it.

The auth service should also have a health check at `/auth/health`.

### 8b. Docker Health Checks

All services should have Docker health checks in docker-compose.prod.yml:

```yaml
  simulator:
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8766/health"]
      interval: 10s
      timeout: 5s
      retries: 3

  cop:
    healthcheck:
      test: ["CMD", "curl", "-sf", "http://localhost:3000/"]
      interval: 30s
      timeout: 5s
      retries: 3

  auth-service:
    healthcheck:
      test: ["CMD", "curl", "-sf", "http://localhost:8080/auth/health"]
      interval: 30s
      timeout: 5s
      retries: 3

  nginx:
    healthcheck:
      test: ["CMD", "curl", "-sf", "http://localhost:80/health"]
      interval: 30s
      timeout: 5s
      retries: 3
```

### 8c. Log Aggregation

Docker log rotation is configured in `/etc/docker/daemon.json` (see
ec2-setup.sh). For this stage, `docker compose logs` is sufficient.

If more is needed later, add a Loki + Grafana stack or ship logs to
CloudWatch.

---

## Human Tasks Checklist (David)

These are the steps David must do manually — Claude Code cannot do these:

### AWS

- [ ] Launch EC2 instance (Ubuntu 24.04, t3.small works for dev/review, t3.medium+ for production)
- [ ] Allocate an Elastic IP and associate it with the instance
- [ ] Configure Security Group: SSH (your IP), HTTP (0.0.0.0/0), HTTPS (0.0.0.0/0)
- [ ] SSH in and run `ec2-setup.sh`
- [ ] Note the Elastic IP address for Cloudflare DNS

### Cloudflare

- [ ] Add DNS record: `ec2sim` → A record → EC2 Elastic IP → Proxied (orange cloud)
- [ ] Set SSL mode to "Full (strict)"
- [ ] Generate Origin Certificate for `ec2sim.brumbiesoft.org`
- [ ] Save `origin.pem` and `origin-key.pem` to `nginx/ssl/` on the server
- [ ] Optional: Enable "Always Use HTTPS"
- [ ] Optional: Enable "Automatic HTTPS Rewrites"
- [ ] Optional: Set minimum TLS version to 1.2
- [ ] Optional: Enable Bot Fight Mode

### First Deployment

- [ ] Clone repo to `/opt/edge-c2-sim` on EC2
- [ ] Copy `.env.production.example` → `.env` and fill in all values
- [ ] Generate JWT_SECRET: `python3 -c "import secrets; print(secrets.token_hex(32))"`
- [ ] Set a strong ADMIN_PASSWORD
- [ ] Add your Cesium Ion token
- [ ] Place Cloudflare origin certs in `nginx/ssl/`
- [ ] Run: `docker compose -f docker-compose.prod.yml up -d --build`
- [ ] Test: Open `https://ec2sim.brumbiesoft.org` — should see login page
- [ ] Log in with admin credentials
- [ ] Verify COP loads and simulator is running

### Grant Claude Access

- [ ] Create a viewer account for Claude: use `sim-add-user` command
- [ ] Share credentials with Claude in chat (username + password)
- [ ] Claude will navigate to the URL and authenticate via the login page

---

## File Summary

Files Claude Code needs to create:

```
auth/
├── main.py              # FastAPI auth service
├── models.py            # User model + JSON file storage
├── config.py            # Environment-based config
├── requirements.txt     # Python dependencies
├── Dockerfile           # Auth service container
└── templates/
    └── login.html       # Login page (dark theme)

nginx/
├── nginx.conf           # Reverse proxy configuration
├── Dockerfile           # Nginx container
└── ssl/
    └── .gitignore       # *.pem, *.key

scripts/
├── ec2-setup.sh         # Server provisioning
├── deploy.sh            # Deployment automation
└── server-commands.sh   # Quick management aliases

docker-compose.prod.yml  # Production compose file
.env.production.example  # Template for production env vars
```

Files to modify:
```
cop/src/config.js        # Auto-detect WSS URL in production
simulator/transport/websocket_adapter.py  # Add JWT validation
.gitignore               # Add .env, *.pem, *.key
```

---

## Implementation Order

1. **Auth service** (Task 1) — get login working locally first
2. **Nginx reverse proxy** (Task 2) — test locally with docker-compose
3. **Production docker-compose** (Task 3) — combine everything
4. **WebSocket URL auto-detection** (Task 2c) — update COP frontend
5. **WebSocket JWT validation** (Task 1f) — update simulator
6. **EC2 setup script** (Task 4) — server provisioning
7. **Deploy script** (Task 6) — automated deployment
8. **Security hardening** (Task 7) — final pass
9. **Test end-to-end** — full deployment test

Local testing: Use `docker-compose.prod.yml` locally with self-signed
certs to verify everything works before deploying to EC2. The login
flow, WebSocket auth, and Nginx routing should all work on localhost
(just with browser cert warnings).

---

## Definition of Done

1. `https://ec2sim.brumbiesoft.org` shows a professional login page
2. Login with valid credentials → redirects to COP dashboard
3. COP loads, connects to WebSocket, shows simulation running
4. Invalid credentials → error message, stays on login page
5. Unauthenticated access to any page → redirected to login
6. WebSocket rejects connections without valid JWT
7. `/health` endpoint accessible without auth (for monitoring)
8. Admin can create/delete user accounts
9. All secrets are in .env, not in code or Docker images
10. SSH is restricted to specific IPs
11. fail2ban is active and banning brute force attempts
12. Docker containers restart automatically on failure
13. Logs are rotated and don't fill the disk
