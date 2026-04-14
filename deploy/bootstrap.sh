#!/usr/bin/env bash
# Marco Droplet bootstrap — idempotent, safe to re-run.
#
# USAGE (on a fresh Ubuntu 24.04 Droplet, as root):
#
#   curl -sSL https://raw.githubusercontent.com/nuriygold/marco/claude/marco-ui-server/deploy/bootstrap.sh \
#     | sudo bash -s -- \
#       --repo https://github.com/nuriygold/marco.git \
#       --branch claude/marco-ui-server \
#       --hostname marco.nuriy.com
#
# Or, if the repo is already cloned on the Droplet:
#
#   sudo bash deploy/bootstrap.sh --hostname marco.nuriy.com
#
# Flags:
#   --repo URL       git clone URL (optional if repo already present)
#   --branch NAME    branch to check out (default: main)
#   --hostname HOST  Caddy hostname for auto-HTTPS (default: <ip>.sslip.io)
#   --skip-caddy     do not configure Caddy (just Python + systemd)
#
# What it does:
#   1. Creates unprivileged 'marco' user + copies root's SSH keys
#   2. Installs python3, python3-venv, git, caddy, ufw
#   3. Enables ufw (ssh + http + https) and creates 2GB swap
#   4. Clones / updates the repo into /home/marco/marco on the chosen branch
#   5. Creates venv + pip installs deploy/requirements.txt
#   6. Generates MARCO_UI_TOKEN + MARCO_UI_SECRET, writes /etc/marco/marco.env
#   7. Installs systemd unit + starts the service
#   8. Configures Caddy with the chosen hostname (unless --skip-caddy)
#   9. Prints the token and the URL to visit

set -euo pipefail

REPO=""
BRANCH="main"
HOSTNAME=""
SKIP_CADDY=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo) REPO="$2"; shift 2 ;;
    --branch) BRANCH="$2"; shift 2 ;;
    --hostname) HOSTNAME="$2"; shift 2 ;;
    --skip-caddy) SKIP_CADDY=1; shift ;;
    -h|--help) sed -n '2,30p' "$0"; exit 0 ;;
    *) echo "Unknown flag: $1" >&2; exit 1 ;;
  esac
done

if [[ $EUID -ne 0 ]]; then
  echo "Run as root (or with sudo)." >&2
  exit 1
fi

log() { printf '\n\e[1;32m[marco-bootstrap]\e[0m %s\n' "$*"; }
warn() { printf '\n\e[1;33m[marco-bootstrap]\e[0m %s\n' "$*" >&2; }

MARCO_HOME="/home/marco"
MARCO_REPO="${MARCO_HOME}/marco"
VENV_DIR="${MARCO_REPO}/.venv"
ENV_FILE="/etc/marco/marco.env"
SYSTEMD_UNIT="/etc/systemd/system/marco.service"

# --- 1. User ---------------------------------------------------------------

if id marco >/dev/null 2>&1; then
  log "User 'marco' already exists."
else
  log "Creating user 'marco'..."
  adduser --disabled-password --gecos "" marco
fi

if [[ -f /root/.ssh/authorized_keys ]]; then
  mkdir -p "${MARCO_HOME}/.ssh"
  cp /root/.ssh/authorized_keys "${MARCO_HOME}/.ssh/authorized_keys"
  chown -R marco:marco "${MARCO_HOME}/.ssh"
  chmod 700 "${MARCO_HOME}/.ssh"
  chmod 600 "${MARCO_HOME}/.ssh/authorized_keys"
fi

# --- 2. System deps --------------------------------------------------------

log "Installing apt packages..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip git curl ufw debian-keyring debian-archive-keyring apt-transport-https

if [[ $SKIP_CADDY -eq 0 ]] && ! command -v caddy >/dev/null 2>&1; then
  log "Installing Caddy..."
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
    | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
    > /etc/apt/sources.list.d/caddy-stable.list
  apt-get update -qq
  apt-get install -y -qq caddy
fi

# --- 3. Firewall + swap ----------------------------------------------------

log "Configuring firewall..."
ufw allow OpenSSH >/dev/null
ufw allow 80/tcp >/dev/null
ufw allow 443/tcp >/dev/null
echo "y" | ufw enable >/dev/null || true

if ! swapon --show | grep -q /swapfile; then
  log "Creating 2GB swap file..."
  fallocate -l 2G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile >/dev/null
  swapon /swapfile
  grep -q '/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
else
  log "Swap already present."
fi

# --- 4. Repo clone / update ------------------------------------------------

if [[ -d "${MARCO_REPO}/.git" ]]; then
  log "Repo present; fetching latest on branch ${BRANCH}..."
  sudo -u marco git -C "${MARCO_REPO}" fetch --all --quiet
  sudo -u marco git -C "${MARCO_REPO}" checkout "${BRANCH}"
  sudo -u marco git -C "${MARCO_REPO}" pull --ff-only --quiet
elif [[ -n "${REPO}" ]]; then
  log "Cloning ${REPO} into ${MARCO_REPO}..."
  sudo -u marco git clone --branch "${BRANCH}" "${REPO}" "${MARCO_REPO}"
else
  echo "No repo at ${MARCO_REPO} and --repo not provided." >&2
  exit 1
fi

# --- 5. Python venv --------------------------------------------------------

log "Creating/updating Python venv..."
sudo -u marco python3 -m venv "${VENV_DIR}"
sudo -u marco "${VENV_DIR}/bin/pip" install --quiet --upgrade pip
sudo -u marco "${VENV_DIR}/bin/pip" install --quiet -r "${MARCO_REPO}/deploy/requirements.txt"

# --- 6. Token + env file ---------------------------------------------------

mkdir -p /etc/marco
if [[ ! -f "${ENV_FILE}" ]]; then
  log "Generating MARCO_UI_TOKEN and MARCO_UI_SECRET..."
  TOKEN=$(openssl rand -hex 32)
  SECRET=$(openssl rand -hex 32)
  cat > "${ENV_FILE}" <<EOF
MARCO_UI_TOKEN=${TOKEN}
MARCO_UI_SECRET=${SECRET}
EOF
  chmod 600 "${ENV_FILE}"
  chown marco:marco "${ENV_FILE}"
else
  log "Env file already exists at ${ENV_FILE} (not overwriting)."
  TOKEN=$(grep '^MARCO_UI_TOKEN=' "${ENV_FILE}" | cut -d= -f2-)
fi

# --- 7. systemd ------------------------------------------------------------

log "Installing systemd unit..."
cp "${MARCO_REPO}/deploy/systemd/marco.service" "${SYSTEMD_UNIT}"
systemctl daemon-reload
systemctl enable --now marco
sleep 1
if ! systemctl is-active --quiet marco; then
  warn "marco.service is not active. Recent logs:"
  journalctl -u marco -n 30 --no-pager || true
  exit 1
fi
log "marco.service is active."

# --- 8. Caddy --------------------------------------------------------------

if [[ $SKIP_CADDY -eq 0 ]]; then
  if [[ -z "${HOSTNAME}" ]]; then
    PUBLIC_IP=$(curl -s https://ifconfig.me || hostname -I | awk '{print $1}')
    HOSTNAME="$(echo "${PUBLIC_IP}" | tr '.' '-').sslip.io"
    log "No --hostname given; defaulting to ${HOSTNAME} (Let's Encrypt via sslip.io)."
  fi
  log "Configuring Caddy for ${HOSTNAME}..."
  sed "s/marco\.example\.com/${HOSTNAME}/g" "${MARCO_REPO}/deploy/Caddyfile" > /etc/caddy/Caddyfile
  systemctl reload caddy || systemctl restart caddy
fi

# --- 9. Summary ------------------------------------------------------------

PUBLIC_IP=$(curl -s https://ifconfig.me || hostname -I | awk '{print $1}')
cat <<EOF

===========================================================================
  Marco is up.

  Systemd:     sudo systemctl status marco
  Logs:        sudo journalctl -u marco -f
  IP:          ${PUBLIC_IP}
EOF
if [[ $SKIP_CADDY -eq 0 ]]; then
  echo "  URL:         https://${HOSTNAME}/login"
else
  echo "  URL:         http://${PUBLIC_IP}:8765/login  (after opening port 8765 in ufw)"
fi
cat <<EOF

  Token (paste on the login page):
    ${TOKEN}

  Workspaces registry: /home/marco/.marco/workspaces.json
  Audit log:           /home/marco/.marco/audit.log
  To update Marco later:
    cd /home/marco/marco && sudo -u marco git pull && \\
      sudo -u marco ${VENV_DIR}/bin/pip install -r deploy/requirements.txt && \\
      sudo systemctl restart marco
===========================================================================
EOF
