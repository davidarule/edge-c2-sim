#!/bin/bash
# EC2 Instance Setup Script for Edge C2 Simulator
#
# Run this on a fresh Ubuntu 24.04 EC2 instance.
# Tested on: t3.small (2 vCPU, 2GB RAM) — minimum for dev/review (swap required)
# Recommended for production: t3.medium+ (2 vCPU, 4GB RAM)
#
# Usage:
#   1. SSH into your EC2 instance
#   2. Copy this script: scp scripts/ec2-setup.sh ubuntu@<ec2-ip>:~/
#   3. Run: chmod +x ec2-setup.sh && sudo ./ec2-setup.sh

set -euo pipefail

echo "╔══════════════════════════════════════════════╗"
echo "║  Edge C2 Simulator — EC2 Setup               ║"
echo "╚══════════════════════════════════════════════╝"

# --- System Update ---
echo "[1/9] Updating system packages..."
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
