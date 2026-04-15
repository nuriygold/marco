# Marco — staging droplet

Marco is deployed to a single DigitalOcean Droplet (see `deploy/README.md`).
That repo layout doesn't produce per-PR preview URLs the way Vercel or Netlify
do — a droplet is a long-lived VM. This doc covers two ways to get
"preview-like" behavior without leaving DO.

## Option A — preview a branch on the production droplet

Cheapest path when you want to eyeball a branch for a few minutes. No extra
infra; production is briefly running the branch.

```bash
ssh marco@<prod-droplet>
cd /home/marco/marco
./deploy/update.sh claude/add-workspace-console-HiwYI   # pulls + restarts
# ...poke around marco.example.com...
./deploy/update.sh main                                  # roll back
```

`update.sh` is idempotent and re-runs `pip install` only if
`deploy/requirements.txt` changed.

**When this is fine:** the change is visual-only, easy to roll back, and you
don't mind production users seeing it for a minute.

**When it isn't:** database migrations, long-running sessions, anything you'd
hate to debug against live traffic.

## Option B — dedicated staging droplet

For real preview behavior: a second droplet at a different hostname (e.g.
`staging.marco.example.com`) that tracks whatever branch you want.

### Sizing & cost

- 1 vCPU / 1 GB RAM droplet is enough — $6/mo at time of writing.
- Use the same Ubuntu 24.04 LTS image as prod.

### One-time setup

Run through `deploy/README.md` on the new droplet with these diffs:

1. **DNS** — point `staging.marco.example.com` (or any subdomain) at the new
   droplet's IP. Caddy will fetch a Let's Encrypt cert automatically.
2. **Caddyfile** — replace the hostname:
   ```caddy
   staging.marco.example.com {
       # same config as prod
       reverse_proxy 127.0.0.1:8765 { ... }
   }
   ```
3. **Repo checkout** — clone the same fork to `/home/marco/marco`. After the
   clone, check out the branch you want to stage:
   ```bash
   cd /home/marco/marco
   git checkout claude/add-workspace-console-HiwYI
   ```
4. **Env file** — use a different `MARCO_UI_TOKEN` than production. Staging
   data lives in `/home/marco/.marco/` just like prod, so there's no bleed
   between the two.
5. **Workspaces** — on first boot Marco auto-registers the droplet's own repo.
   Add staging-safe workspaces only. Never point staging at a production repo.

### Per-PR preview workflow

On the staging droplet:

```bash
# Preview a PR branch.
./deploy/update.sh claude/some-feature-branch

# Switch back to main when done.
./deploy/update.sh main
```

`update.sh` detects the branch flip and restarts the systemd unit only when
something actually changed.

### Automating it (optional)

If you want "push to branch → staging updates" without SSHing in:

1. Add an SSH deploy key for the `marco` user on the staging droplet with
   read access to the repo.
2. Add a GitHub Actions workflow that `ssh`es into the staging droplet and
   runs `./deploy/update.sh ${{ github.head_ref }}` on PR events.
3. The staging droplet now mirrors whichever branch most recently triggered
   the workflow.

This is not wired up in the repo today — the hook is intentionally not
automatic so a PR can't silently replace staging while someone else is using
it. Add it when the team grows past one person.

## Option C — move to a platform with built-in previews

If per-PR URLs become a real need, the droplet model is the wrong tool.
Drop-in alternatives that keep a FastAPI + HTMX app happy:

| Platform | Preview model | Notes |
|---|---|---|
| DigitalOcean App Platform | Preview app per PR | Stays in DO; 1-click from the existing droplet setup. |
| Fly.io | `fly deploy --app <pr-slug>` | Generous free tier, fast cold starts. |
| Render | Preview environments on PR | Similar UX to Vercel; docker-based. |

Each of these replaces the `deploy/` directory entirely; they're "move off the
droplet" decisions, not add-ons.

## Operational notes

- Staging should never have write access to production data. Each droplet has
  its own `/home/marco/.marco/` — don't share it via NFS or similar.
- Staging's audit log (`~/.marco/audit.log`) is where you verify that
  experimental patches behaved. Keep it; don't clear it between runs.
- Rotate the staging `MARCO_UI_TOKEN` on a different cadence than prod so a
  leaked staging token can't unlock production.
