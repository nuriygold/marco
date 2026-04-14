# Marco UI — Droplet deployment

Step-by-step setup for a single DigitalOcean Droplet. Tested shape: Ubuntu
24.04 LTS, 1 vCPU / 2 GB RAM / 50 GB SSD ($12/mo at the time of writing).

## 1. Create the Droplet

- Size: 1 vCPU / 2 GB RAM / 50 GB SSD (Basic shared, $12/mo).
- Image: Ubuntu 24.04 LTS.
- Add your SSH key during creation.
- Region: closest to you.
- Enable the firewall after boot (see step 3).

## 2. First SSH + user setup

SSH in as root:

```bash
ssh root@<droplet-ip>
```

Create an unprivileged service user and give it your SSH key:

```bash
adduser --disabled-password --gecos "" marco
mkdir -p /home/marco/.ssh
cp /root/.ssh/authorized_keys /home/marco/.ssh/
chown -R marco:marco /home/marco/.ssh
chmod 700 /home/marco/.ssh
chmod 600 /home/marco/.ssh/authorized_keys
```

Log back in as `marco` from now on:

```bash
ssh marco@<droplet-ip>
```

## 3. Firewall + swap

```bash
# Enable ufw — allow SSH, HTTP, HTTPS only.
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable

# 2 GB swap file is worth having on a 2 GB droplet.
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

## 4. System dependencies

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git

# Caddy (from official repo)
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
  | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
  | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update
sudo apt install -y caddy

# Rust (only if you want to build/run the rust/ workspace on the Droplet too).
# Skip this block if you only need the Python server.
# curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
```

## 5. Clone the repo and install Python deps

```bash
cd /home/marco
git clone <your-fork-url> marco
cd marco
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r deploy/requirements.txt
```

Verify the CLI boots (no server):

```bash
.venv/bin/python -m src.main doctor
```

## 6. Configure the server secret

Generate a strong token and write it to `/etc/marco/marco.env`:

```bash
sudo mkdir -p /etc/marco
TOKEN=$(openssl rand -hex 32)
SECRET=$(openssl rand -hex 32)
sudo tee /etc/marco/marco.env >/dev/null <<EOF
MARCO_UI_TOKEN=$TOKEN
MARCO_UI_SECRET=$SECRET
EOF
sudo chmod 600 /etc/marco/marco.env
sudo chown marco:marco /etc/marco/marco.env
echo "Your Marco token:"
echo "$TOKEN"
```

Save the token somewhere you can paste into the browser later.

## 7. Install the systemd unit

```bash
sudo cp deploy/systemd/marco.service /etc/systemd/system/marco.service
sudo systemctl daemon-reload
sudo systemctl enable --now marco
sudo systemctl status marco
```

You should see `active (running)`. `journalctl -u marco -f` streams logs.

## 8. Configure Caddy

Copy and edit the Caddyfile (replace the hostname):

```bash
sudo cp deploy/Caddyfile /etc/caddy/Caddyfile
sudo nano /etc/caddy/Caddyfile  # replace marco.example.com with your host
sudo systemctl reload caddy
```

Point an `A` record for your chosen hostname at the Droplet's IP. Caddy
fetches a Let's Encrypt cert on first request.

## 9. First login

Visit `https://marco.example.com/login`, paste the token from step 6. Marco
auto-registers the Droplet's Marco repo as the first workspace. Use the
**Add workspace** form in the sidebar to register any other repos you want to
operate on (absolute paths on the Droplet filesystem).

## 10. Updating Marco

```bash
cd /home/marco/marco
git pull
.venv/bin/pip install -r deploy/requirements.txt
sudo systemctl restart marco
```

## Operational notes

- **Data:** workspace registry lives in `/home/marco/.marco/workspaces.json`;
  audit log at `/home/marco/.marco/audit.log`. Each workspace has its own
  `.marco/` directory inside the repo for patches, sessions, and memory.
- **Safety:** the server forces `safety_mode=workspace-write` regardless of
  any repo's `.marco/config.json`. `danger-full-access` is not reachable over
  HTTP in this branch.
- **Patches:** applying a patch via the UI requires typing the patch name in
  the confirm box and is logged to the audit trail. Rollbacks are one-click
  but also logged.
- **Scripts:** `POST /api/scripts/<name>/run` requires `{execute: true,
  confirm: true}` and is restricted to the allow-listed prefixes in
  `config.ALLOWED_SCRIPT_PREFIXES`.
- **Secrets rotation:** to rotate the login token, edit `/etc/marco/marco.env`
  and `sudo systemctl restart marco`. Existing browser sessions will be
  invalidated.
