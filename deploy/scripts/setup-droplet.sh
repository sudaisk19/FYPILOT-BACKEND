#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# FYPilot Backend - DigitalOcean Droplet Initial Setup Script
# Run this ONCE on a fresh Ubuntu 22.04/24.04 droplet
# Usage: ssh root@your-droplet-ip 'bash -s' < deploy/scripts/setup-droplet.sh
# ═══════════════════════════════════════════════════════════════

set -euo pipefail

echo "═══════════════════════════════════════════════════"
echo "  FYPilot Backend - Droplet Setup"
echo "═══════════════════════════════════════════════════"

# ─── 1. System Update ──────────────────────────────────────
echo ""
echo "📦 Step 1: Updating system packages..."
apt-get update && apt-get upgrade -y

# ─── 2. Install Essential Packages ─────────────────────────
echo ""
echo "📦 Step 2: Installing essential packages..."
apt-get install -y \
    curl \
    wget \
    git \
    ufw \
    fail2ban \
    nginx \
    certbot \
    python3-certbot-nginx \
    htop \
    unzip \
    jq

# ─── 3. Install Docker ─────────────────────────────────────
echo ""
echo "🐳 Step 3: Installing Docker..."
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com | sh
    systemctl enable docker
    systemctl start docker
    echo "Docker installed successfully."
else
    echo "Docker already installed."
fi

# Install Docker Compose plugin
if ! docker compose version &> /dev/null; then
    apt-get install -y docker-compose-plugin
    echo "Docker Compose plugin installed."
else
    echo "Docker Compose already installed."
fi

# ─── 4. Create deploy user ─────────────────────────────────
echo ""
echo "👤 Step 4: Creating deploy user..."
if ! id "deploy" &>/dev/null; then
    useradd -m -s /bin/bash -G docker,sudo deploy
    echo "deploy ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/deploy
    mkdir -p /home/deploy/.ssh
    cp /root/.ssh/authorized_keys /home/deploy/.ssh/authorized_keys 2>/dev/null || true
    chown -R deploy:deploy /home/deploy/.ssh
    chmod 700 /home/deploy/.ssh
    chmod 600 /home/deploy/.ssh/authorized_keys 2>/dev/null || true
    echo "User 'deploy' created and added to docker group."
else
    echo "User 'deploy' already exists."
fi

# ─── 5. Configure Firewall ─────────────────────────────────
echo ""
echo "🔥 Step 5: Configuring firewall..."
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp    # SSH
ufw allow 80/tcp    # HTTP
ufw allow 443/tcp   # HTTPS
ufw --force enable
echo "Firewall configured (SSH, HTTP, HTTPS only)."

# ─── 6. Configure fail2ban ─────────────────────────────────
echo ""
echo "🛡️ Step 6: Configuring fail2ban..."
cat > /etc/fail2ban/jail.local << 'EOF'
[DEFAULT]
bantime = 3600
findtime = 600
maxretry = 5

[sshd]
enabled = true
port = ssh
logpath = /var/log/auth.log
maxretry = 3
bantime = 7200
EOF
systemctl enable fail2ban
systemctl restart fail2ban
echo "fail2ban configured."

# ─── 7. Create project directory ───────────────────────────
echo ""
echo "📁 Step 7: Creating project directory..."
mkdir -p /opt/fypilot-backend
chown deploy:deploy /opt/fypilot-backend

# ─── 8. Setup Nginx ────────────────────────────────────────
echo ""
echo "🌐 Step 8: Setting up Nginx..."
# Remove default site
rm -f /etc/nginx/sites-enabled/default

# Create certbot webroot
mkdir -p /var/www/certbot

# Test nginx config
nginx -t
systemctl enable nginx
systemctl restart nginx
echo "Nginx configured."

# ─── 9. Setup log rotation ─────────────────────────────────
echo ""
echo "📝 Step 9: Setting up log rotation..."
cat > /etc/logrotate.d/fypilot << 'EOF'
/var/log/fypilot/*.log {
    daily
    missingok
    rotate 14
    compress
    delaycompress
    notifempty
    create 0640 deploy deploy
    sharedscripts
}
EOF
mkdir -p /var/log/fypilot
chown deploy:deploy /var/log/fypilot

# ─── 10. Create deployment helper script ───────────────────
echo ""
echo "📝 Step 10: Creating deployment helper script..."
cat > /opt/fypilot-backend/deploy.sh << 'DEPLOY_SCRIPT'
#!/bin/bash
# Manual deployment helper script
set -e

echo "🚀 Manual deployment..."

cd /opt/fypilot-backend

# Pull latest image
docker compose pull

# Restart with new image
docker compose down --timeout 30
docker compose up -d

# Wait for health
echo "⏳ Waiting for health check..."
for i in $(seq 1 30); do
    if curl -sf http://localhost:8000/api/health > /dev/null 2>&1; then
        echo "✅ Application is healthy!"
        break
    fi
    if [ $i -eq 30 ]; then
        echo "❌ Health check failed"
        docker compose logs --tail=50
        exit 1
    fi
    sleep 2
done

# Clean old images
docker image prune -f

echo "🎉 Deployment complete!"
DEPLOY_SCRIPT
chmod +x /opt/fypilot-backend/deploy.sh

echo ""
echo "═══════════════════════════════════════════════════"
echo "  ✅ Droplet setup complete!"
echo "═══════════════════════════════════════════════════"
echo ""
echo "  Next steps:"
echo "  1. Copy your .env file:       scp .env deploy@YOUR_IP:/opt/fypilot-backend/.env"
echo "  2. Copy docker-compose:       scp deploy/docker-compose.prod.yml deploy@YOUR_IP:/opt/fypilot-backend/docker-compose.yml"
echo "  3. Copy nginx config:         scp deploy/nginx/fypilot-backend.conf root@YOUR_IP:/etc/nginx/sites-available/fypilot-backend"
echo "  4. Enable nginx site:         ssh root@YOUR_IP 'ln -sf /etc/nginx/sites-available/fypilot-backend /etc/nginx/sites-enabled/ && nginx -t && systemctl reload nginx'"
echo "  5. Setup SSL:                 ssh root@YOUR_IP 'certbot --nginx -d api.fypilot.com'"
echo "  6. Add GitHub Secrets (see DIGITALOCEAN_DEPLOYMENT.md)"
echo ""
