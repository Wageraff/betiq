#!/bin/bash
# Node.js 20 LTS for building admin-ui (Vite 5 needs Node >= 18).
# Usage: sudo bash deploy/scripts/install_node20.sh
set -euo pipefail

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root: sudo bash $0"
  exit 1
fi

if command -v node &>/dev/null; then
  major="$(node -e 'console.log(parseInt(process.versions.node.split(".")[0], 10))')"
  if [[ "$major" -ge 18 ]]; then
    echo "Node $(node -v) already OK (>= 18)"
    exit 0
  fi
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq ca-certificates curl gnupg

# NodeSource Node 20.x (Ubuntu/Debian)
install -d /etc/apt/keyrings
curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg
echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_20.x nodistro main" \
  > /etc/apt/sources.list.d/nodesource.list
apt-get update -qq
apt-get install -y -qq nodejs

echo "Installed: $(node -v) $(npm -v)"
echo "Rebuild admin UI: cd /opt/betiq/admin-ui && npm install && npm run build"
