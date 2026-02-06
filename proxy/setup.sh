#!/bin/bash
# Beget VPS setup script for AI API proxy
# Run as root on Ubuntu 22.04
# Usage: bash setup.sh proxy.alchemya-trainer.ru

set -euo pipefail

DOMAIN="${1:-proxy.alchemya-trainer.ru}"

echo "=== Setting up AI API Proxy on ${DOMAIN} ==="

# 1. Update system
echo "[1/5] Updating system..."
apt update && apt upgrade -y

# 2. Install Nginx + Certbot
echo "[2/5] Installing Nginx and Certbot..."
apt install -y nginx certbot python3-certbot-nginx ufw

# 3. Configure firewall
echo "[3/5] Configuring firewall..."
ufw allow OpenSSH
ufw allow 'Nginx Full'
ufw --force enable

# 4. Deploy Nginx config
echo "[4/5] Deploying Nginx configuration..."
cp nginx.conf "/etc/nginx/sites-available/proxy"
ln -sf /etc/nginx/sites-available/proxy /etc/nginx/sites-enabled/proxy
rm -f /etc/nginx/sites-enabled/default

# Test config
nginx -t

# Reload
systemctl reload nginx

# 5. SSL certificate
echo "[5/5] Obtaining SSL certificate..."
certbot --nginx -d "${DOMAIN}" --non-interactive --agree-tos --email admin@alchemya.ru

# Enable auto-renewal
systemctl enable certbot.timer

echo ""
echo "=== Setup complete! ==="
echo "Proxy URL: https://${DOMAIN}"
echo ""
echo "Test endpoints:"
echo "  curl https://${DOMAIN}/health"
echo "  curl https://${DOMAIN}/anthropic/v1/messages (with API key)"
echo "  curl https://${DOMAIN}/openai/v1/models (with API key)"
echo ""
echo "WebSocket (voice mode): wss://${DOMAIN}/realtime"
