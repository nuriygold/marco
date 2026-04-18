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

### (Optional) Enable the AI layer — Console + AI plan + patch-suggest

Marco supports three LLM providers, selected via `MARCO_LLM_PROVIDER`:

| Provider value | Use for |
|---|---|
| `azure-openai` | Classic Azure OpenAI (e.g. GPT-5.3 on `.cognitiveservices.azure.com`) |
| `azure-foundry` | Azure AI Foundry's OpenAI-compatible endpoint (e.g. Grok, Llama, GPT-OSS on `.services.ai.azure.com/openai/v1`) |
| `grok` | Direct xAI API at `api.x.ai/v1` |

Pick one in `/etc/marco/marco.env`:

#### Azure OpenAI

```bash
sudo tee -a /etc/marco/marco.env >/dev/null <<'EOF'
MARCO_LLM_PROVIDER=azure-openai
AZURE_OPENAI_API_KEY=<your-azure-openai-key>
AZURE_OPENAI_ENDPOINT=https://<your-resource>.cognitiveservices.azure.com
AZURE_OPENAI_DEPLOYMENT=<your-deployment-name>
AZURE_OPENAI_API_VERSION=2024-12-01-preview
EOF
sudo systemctl restart marco
```

**Azure model recommendations:**

| Deployment | Good for Marco? | Notes |
|---|---|---|
| `gpt-5.3-chat` / `gpt-5-chat` | ✅ Excellent | Best verbatim reproduction for patch find/replace |
| `gpt-4o` | ✅ Good | Solid all-rounder |
| `gpt-4o-mini` | ⚠️ Weak | Cheap but unreliable for patches |
| `gpt-3.5-turbo` | ❌ Skip | Too weak for patch verbatim work |

#### Azure AI Foundry (Grok / Llama / GPT-OSS via Azure)

If your Grok/Llama/etc. deployment lives on Azure's unified OpenAI-compatible
endpoint (`.services.ai.azure.com/openai/v1/`), use this provider:

```bash
sudo tee -a /etc/marco/marco.env >/dev/null <<'EOF'
MARCO_LLM_PROVIDER=azure-foundry
AZURE_FOUNDRY_API_KEY=<your-azure-key>
AZURE_FOUNDRY_ENDPOINT=https://<your-resource>.services.ai.azure.com/openai/v1
AZURE_FOUNDRY_MODEL=grok-4-fast-reasoning
EOF
sudo systemctl restart marco
```

**Azure Foundry model recommendations for Marco:**

| Deployment name | Good for Marco? | Notes |
|---|---|---|
| `grok-4-fast-reasoning` | ✅✅ Excellent | Reasoning helps patch precision + plan quality |
| `grok-4` | ✅ Excellent | Flagship, slower/costlier than fast-reasoning |
| `grok-4-fast-non-reasoning` | ✅ Good | Faster / cheaper; fine for plans, less careful on patches |
| `grok-3` | ⚠️ OK | Legacy fallback |

The deployment name you pass here must match what you named it in the Azure
AI Foundry portal.

#### Grok (direct xAI API)

If you access Grok directly through `api.x.ai` (not through Azure), use:

```bash
sudo tee -a /etc/marco/marco.env >/dev/null <<'EOF'
MARCO_LLM_PROVIDER=grok
XAI_API_KEY=<your-xai-key>
XAI_MODEL=grok-4-fast-reasoning
EOF
sudo systemctl restart marco
```

Override `XAI_BASE_URL` if you're using a non-standard xAI endpoint (default
is `https://api.x.ai/v1`).

#### Switching providers

Change `MARCO_LLM_PROVIDER` and `sudo systemctl restart marco`. The AI
status endpoint and the ✨ UI affordances automatically reflect the active
provider. Tools and the Console work identically across both.

#### Notes on API parameters

- GPT-5 / o-series / reasoning models need `max_completion_tokens` instead
  of `max_tokens`. Marco auto-selects based on deployment/model name. Override
  via `MARCO_LLM_MAX_TOKEN_FIELD=max_completion_tokens` if the heuristic misses.
- Retries: 429 and 5xx are retried up to `MARCO_LLM_MAX_RETRIES` times (default 2)
  with exponential backoff. Timeout: `MARCO_LLM_TIMEOUT` seconds (default 60).

### Using the Console

After enabling AI, visit `/console` (top nav item). Type anything in plain
language — Marco picks the right tool and reports back. Examples:

- *"show me the repo status"* → calls `workspace_status`
- *"find all Python files"* → calls `find_files`
- *"where do we use the database?"* → calls `lookup_content`
- *"remember: we use JWT for service auth"* → calls `save_memory`
- *"plan a refactor of the auth flow"* → calls `create_plan` and stages a session
- *"stage a patch that adds a version line to README.md"* → calls `suggest_patch`
  and stages a patch proposal for you to review + type-confirm + apply from
  the Patches page

Every mutation (memory writes, plan creation, patch proposals) is logged to
the audit trail. The console never applies patches or runs scripts — those
still require explicit confirmation via the existing Patches and Scripts UIs.

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

## 10. GitHub Actions CI/CD (DEPLOY_SSH_KEY)

The `.github/workflows/deploy.yml` workflow SSH-es into the Droplet on every
push to `main` and runs `deploy/update.sh`. It needs a dedicated deploy key:

**On the Droplet, as the `marco` user:**

```bash
ssh-keygen -t ed25519 -C 'github-actions-deploy' -f ~/.ssh/deploy_key -N ''
cat ~/.ssh/deploy_key.pub >> ~/.ssh/authorized_keys
cat ~/.ssh/deploy_key   # copy this output
```

**In GitHub — Settings → Secrets and variables → Actions → New repository secret:**

| Name | Value |
|------|-------|
| `DEPLOY_SSH_KEY` | Paste the full private key (including `-----BEGIN/END-----` lines) |

Without this secret the workflow fails immediately with
`can't connect without a private SSH key or password`.

## 11. Updating Marco

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
