#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════
#  Smart Media Fetcher — Ubuntu 22.04 Server Setup Script
#  Run as root: sudo bash setup.sh
# ══════════════════════════════════════════════════════════
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

[[ $EUID -ne 0 ]] && error "Please run as root: sudo bash setup.sh"

info "Starting Smart Media Fetcher server setup..."

# ── 1. System update ──────────────────────────────────────
info "Updating system packages..."
apt-get update -qq && apt-get upgrade -y -qq

# ── 2. Essential tools ────────────────────────────────────
info "Installing essential tools..."
apt-get install -y -qq \
    curl wget git unzip build-essential \
    ca-certificates gnupg lsb-release \
    software-properties-common apt-transport-https

# ── 3. Docker ─────────────────────────────────────────────
if ! command -v docker &>/dev/null; then
    info "Installing Docker..."
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] \
        https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" \
        > /etc/apt/sources.list.d/docker.list
    apt-get update -qq
    apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-compose-plugin
    systemctl enable docker && systemctl start docker
    info "Docker installed: $(docker --version)"
else
    info "Docker already installed: $(docker --version)"
fi

# ── 4. FFmpeg ─────────────────────────────────────────────
info "Installing FFmpeg..."
apt-get install -y -qq ffmpeg
info "FFmpeg installed: $(ffmpeg -version 2>&1 | head -1)"

# ── 5. Create app user ────────────────────────────────────
if ! id "smf" &>/dev/null; then
    info "Creating application user 'smf'..."
    useradd -m -s /bin/bash smf
    usermod -aG docker smf
fi

# ── 6. Create directories ─────────────────────────────────
info "Creating application directories..."
mkdir -p /opt/smart-media-fetcher
mkdir -p /var/log/smf
mkdir -p /tmp/smf_downloads
chown -R smf:smf /opt/smart-media-fetcher /var/log/smf /tmp/smf_downloads

# ── 7. Firewall (UFW) ─────────────────────────────────────
info "Configuring firewall..."
if command -v ufw &>/dev/null; then
    ufw allow OpenSSH
    ufw allow 80/tcp
    ufw allow 443/tcp
    ufw --force enable
    info "Firewall enabled."
fi

# ── 8. Certbot (SSL) ──────────────────────────────────────
if ! command -v certbot &>/dev/null; then
    info "Installing Certbot for SSL..."
    apt-get install -y -qq certbot python3-certbot-nginx
fi

# ── 9. Log rotation ───────────────────────────────────────
cat > /etc/logrotate.d/smf << 'LOGROTATE'
/var/log/smf/*.log {
    daily
    rotate 14
    compress
    delaycompress
    missingok
    notifempty
    create 0640 smf smf
}
LOGROTATE

# ── 10. Systemd service (optional — Docker handles this) ──
cat > /etc/systemd/system/smart-media-fetcher.service << 'SERVICE'
[Unit]
Description=Smart Media Fetcher
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/smart-media-fetcher
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
User=smf
Group=smf

[Install]
WantedBy=multi-user.target
SERVICE

systemctl daemon-reload
systemctl enable smart-media-fetcher

# ── DONE ──────────────────────────────────────────────────
echo ""
echo -e "${GREEN}══════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  Setup complete!${NC}"
echo -e "${GREEN}══════════════════════════════════════════════════${NC}"
echo ""
echo "  Next steps:"
echo "  1. cd /opt/smart-media-fetcher"
echo "  2. git clone <your-repo> ."
echo "  3. cp .env.example .env && nano .env"
echo "  4. docker compose up -d --build"
echo "  5. docker compose exec backend alembic upgrade head"
echo "  6. certbot --nginx -d yourdomain.com"
echo ""
echo "  FFmpeg path: $(which ffmpeg)"
echo "  Docker:      $(docker --version)"
echo ""
