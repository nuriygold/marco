"""Marco UI server — FastAPI wrapper over the v3 CLI.

Single-user operator console. All v3 Python handlers are reused directly;
this module is a thin HTTP + HTML adapter. Deploy target is a single
DigitalOcean Droplet behind Caddy (see ``deploy/``).

The ``MARCO_UI_TOKEN`` env var is required to boot. Every mutation is
recorded to ``~/.marco/audit.log``.
"""

from __future__ import annotations

import asyncio
import json
import re
import shlex
import subprocess
import threading
from dataclasses import asdict
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import Depends, FastAPI, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .autonomy import (
    create_plan,
    execute_plan,
    list_sessions,
    recover_session,
    resume_session,
    validate_session,
)
from .config import ALLOWED_SCRIPT_PREFIXES, SHELL_META, MarcoProfile
from .memory import add_entry, list_entries, recall
from .patches import apply_patch, list_patches, propose_patch, rollback_patch, show_patch
from .repo_intel import (
    architecture_map,
    config_map,
    discover_env_vars,
    discover_routes,
    discover_scripts,
    find_files,
    integration_map,
    lookup_content,
    render_tree,
    scan_repository,
    where_edit,
)
from .scaffold import scaffold_component, scaffold_page, scaffold_route, scaffold_service
from .server_audit import record as audit_record, tail as audit_tail
from .server_auth import (
    COOKIE_NAME,
    AuthConfig,
    load_auth_config,
    sign_cookie,
    verify_form_token,
    verify_request_token,
)
from .server_streaming import format_sse, stream_subprocess, stream_sync_callable
from .server_workspaces import (
    REGISTRY_PATH,
    Workspace,
    add_workspace,
    ensure_workspace_from_cwd,
    get_active,
    load_registry,
    remove_workspace,
    set_active,
)
from .storage import MarcoStorage


TEMPLATES_DIR = Path(__file__).parent / 'templates'
STATIC_DIR = Path(__file__).parent / 'static'

# Server always runs workspace-write. No HTTP surface for danger-full-access.
SERVER_PROFILE = MarcoProfile(safety_mode='workspace-write', pause_before_mutation=False)

# ---------- Light-task classifier -------------------------------------------

_HEAVY_RE = re.compile(
    r'\b(patch|fix|change|update|modify|refactor|plan|implement|add|remove|delete|'
    r'debug|broken|error|fail|bug|issue|wrong|why|how do|create|build|deploy|migrate|generate|'
    r'suggest|stage|propose|review|analyze|analyse|diagnose|improve|rewrite|rename)\b',
    re.IGNORECASE,
)
_LIGHT_RE = re.compile(
    r'\b(show|list|what|who|where|status|check|find|search|recall|get|view|'
    r'display|tell me|describe|print|lookup|look up)\b',
    re.IGNORECASE,
)


def _classify_task(message: str) -> str:
    """Heuristic: returns 'light' (pure lookup) or 'heavy' (reasoning needed).

    Heavy signals take priority so ambiguous messages stay in reasoning mode.
    """
    if _HEAVY_RE.search(message):
        return 'heavy'
    if _LIGHT_RE.search(message):
        return 'light'
    return 'heavy'  # safe default — never silently downgrade


def _require_active_workspace(registry_path: Path = REGISTRY_PATH) -> Workspace:
    ws = get_active(registry_path)
    if ws is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail='No active workspace. POST /api/workspaces to register one.',
        )
    return ws


def _workspace_root(ws: Workspace) -> Path:
    return Path(ws.path)


def _storage_for(ws: Workspace) -> MarcoStorage:
    return MarcoStorage(_workspace_root(ws))


def create_app(*, registry_path: Path = REGISTRY_PATH, auth: AuthConfig | None = None) -> FastAPI:
    app = FastAPI(title='Marco UI', docs_url=None, redoc_url=None)
    app.state.registry_path = registry_path
    app.state.auth = auth or load_auth_config()

    if STATIC_DIR.exists():
        app.mount('/static', StaticFiles(directory=str(STATIC_DIR)), name='static')
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    templates.env.add_extension('jinja2.ext.loopcontrols')
    app.state.templates = templates

    # ---------- Auth ----------

    PUBLIC_PATHS = {'/login', '/healthz', '/favicon.ico'}

    @app.middleware('http')
    async def auth_gate(request: Request, call_next):  # type: ignore[no-untyped-def]
        path = request.url.path
        if path.startswith('/static') or path in PUBLIC_PATHS:
            return await call_next(request)
        cfg: AuthConfig = request.app.state.auth
        bearer = request.headers.get('authorization')
        cookie = request.cookies.get(COOKIE_NAME)
        if not verify_request_token(bearer=bearer, cookie=cookie, config=cfg):
            if path.startswith('/api/'):
                return JSONResponse({'detail': 'unauthorized'}, status_code=401)
            return RedirectResponse(url=f'/login?next={path}', status_code=302)
        return await call_next(request)

    def _active() -> Workspace:
        return _require_active_workspace(request_path := registry_path)

    # ---------- Pages ----------

    @app.get('/healthz')
    async def healthz() -> dict[str, str]:
        return {'status': 'ok'}

    @app.get('/login', response_class=HTMLResponse)
    async def login_form(request: Request, next: str = '/') -> HTMLResponse:
        return templates.TemplateResponse(request, 'login.html', {'next': next, 'error': None})

    @app.post('/login')
    async def login_submit(request: Request, token: str = Form(...), next: str = Form('/')) -> Response:
        cfg: AuthConfig = request.app.state.auth
        if not verify_form_token(token, cfg):
            return templates.TemplateResponse(
                request,
                'login.html',
                {'next': next, 'error': 'Invalid token.'},
                status_code=401,
            )
        signed = sign_cookie(cfg)
        response = RedirectResponse(url=next or '/', status_code=302)
        response.set_cookie(COOKIE_NAME, signed, httponly=True, samesite='lax', secure=False, max_age=60 * 60 * 24 * 14)
        return response

    @app.post('/logout')
    async def logout() -> Response:
        response = RedirectResponse(url='/login', status_code=302)
        response.delete_cookie(COOKIE_NAME)
        return response

    def _page_context(**extra: Any) -> dict[str, Any]:
        registry = load_registry(registry_path)
        active = get_active(registry_path)
        return {'registry': registry, 'active': active, **extra}

    @app.get('/', response_class=HTMLResponse)
    async def dashboard(request: Request) -> HTMLResponse:
        ws = get_active(registry_path)
        if ws is None:
            return templates.TemplateResponse(request, 'no_workspace.html', _page_context())
        storage = _storage_for(ws)
        root = _workspace_root(ws)
        scan = scan_repository(root)
        sessions = list_sessions(storage)
        patches = list_patches(storage)
        pending_patches = [p for p in patches if p.status == 'pending']
        active_sessions = [s for s in sessions if s.status in ('running', 'ready')]
        return templates.TemplateResponse(
            request,
            'dashboard.html',
            _page_context(
                scan=scan,
                pending_patches=pending_patches,
                active_sessions=active_sessions,
                recent_patches=list(reversed(patches))[:10],
                recent_sessions=list(reversed(sessions))[:10],
            ),
        )

    @app.get('/repo', response_class=HTMLResponse)
    async def repo_page(request: Request) -> HTMLResponse:
        ws = _require_active_workspace(registry_path)
        root = _workspace_root(ws)
        return templates.TemplateResponse(
            request,
            'repo.html',
            _page_context(
                scripts=discover_scripts(root),
                env_vars=discover_env_vars(root),
                routes=discover_routes(root),
                tree=render_tree(root, max_depth=3),
                architecture=architecture_map(root),
                configs=config_map(root),
            ),
        )

    @app.get('/memory', response_class=HTMLResponse)
    async def memory_page(request: Request) -> HTMLResponse:
        ws = _require_active_workspace(registry_path)
        storage = _storage_for(ws)
        return templates.TemplateResponse(
            request,
            'memory.html',
            _page_context(
                notes=list_entries(storage, 'note', limit=200),
                decisions=list_entries(storage, 'decision', limit=200),
                conventions=list_entries(storage, 'convention', limit=200),
            ),
        )

    @app.get('/sessions', response_class=HTMLResponse)
    async def sessions_page(request: Request) -> HTMLResponse:
        ws = _require_active_workspace(registry_path)
        storage = _storage_for(ws)
        sessions = list_sessions(storage)
        buckets = {
            'planned': [s for s in sessions if s.phase == 'plan' and s.status == 'ready'],
            'running': [s for s in sessions if s.status == 'running'],
            'blocked': [s for s in sessions if s.status == 'failed'],
            'recoverable': [s for s in sessions if s.phase == 'recover'],
            'resumable': [s for s in sessions if s.status in ('passed', 'ready') and s.phase != 'plan'],
        }
        return templates.TemplateResponse(
            request, 'sessions.html', _page_context(sessions=sessions, buckets=buckets)
        )

    @app.get('/patches', response_class=HTMLResponse)
    async def patches_page(request: Request) -> HTMLResponse:
        ws = _require_active_workspace(registry_path)
        storage = _storage_for(ws)
        patches = list(reversed(list_patches(storage)))
        return templates.TemplateResponse(request, 'patches.html', _page_context(patches=patches))

    @app.get('/patches/{patch_id}', response_class=HTMLResponse)
    async def patch_detail_page(request: Request, patch_id: str) -> HTMLResponse:
        ws = _require_active_workspace(registry_path)
        storage = _storage_for(ws)
        try:
            patch = show_patch(storage, patch_id)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail='patch not found')
        return templates.TemplateResponse(request, 'patch_detail.html', _page_context(patch=patch))

    @app.get('/scripts', response_class=HTMLResponse)
    async def scripts_page(request: Request) -> HTMLResponse:
        ws = _require_active_workspace(registry_path)
        root = _workspace_root(ws)
        return templates.TemplateResponse(
            request, 'scripts.html', _page_context(scripts=discover_scripts(root))
        )

    @app.get('/audit', response_class=HTMLResponse)
    async def audit_page(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            request, 'audit.html', _page_context(entries=audit_tail(limit=200))
        )

    @app.get('/help', response_class=HTMLResponse)
    async def help_page(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(request, 'help.html', _page_context())

    # ---------- API: workspaces ----------

    @app.get('/api/workspaces')
    async def api_list_workspaces() -> dict[str, Any]:
        registry = load_registry(registry_path)
        return {
            'active': registry.active,
            'workspaces': [asdict(ws) for ws in registry.workspaces],
        }

    @app.get('/api/workspaces/candidates')
    async def api_workspace_candidates() -> dict[str, Any]:
        """List git repos under MARCO_WORKSPACE_ROOT (default: ~) not yet registered.

        Read-only; a one-level scan capped at 50 entries. Used by the sidebar's
        quick-add UI so operators don't have to type absolute paths.
        """
        import os
        from pathlib import Path as _P

        root = _P(os.environ.get('MARCO_WORKSPACE_ROOT', str(_P.home()))).expanduser()
        registry = load_registry(registry_path)
        registered_paths = {_P(ws.path).resolve() for ws in registry.workspaces}
        registered_names = {ws.name for ws in registry.workspaces}

        candidates: list[dict[str, str]] = []
        if root.exists() and root.is_dir():
            try:
                entries = sorted(os.scandir(root), key=lambda e: e.name.lower())
            except PermissionError:
                entries = []
            for entry in entries:
                if len(candidates) >= 50:
                    break
                if not entry.is_dir(follow_symlinks=False):
                    continue
                path = _P(entry.path).resolve()
                if not (path / '.git').exists():
                    continue
                if path in registered_paths:
                    continue
                name = entry.name
                # Skip candidates whose nickname collides with an existing workspace.
                if name in registered_names:
                    continue
                candidates.append({'name': name, 'path': str(path)})
        return {'root': str(root), 'candidates': candidates}

    @app.post('/api/workspaces')
    async def api_add_workspace(payload: dict[str, str]) -> dict[str, Any]:
        name = payload.get('name') or ''
        path = payload.get('path') or ''
        if not name or not path:
            raise HTTPException(status_code=400, detail='name and path are required')
        try:
            ws = add_workspace(name, Path(path), registry_path)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        audit_record('workspace.add', workspace=ws.name, params={'path': ws.path})
        return asdict(ws)

    @app.post('/api/workspaces/active')
    async def api_set_active(payload: dict[str, str]) -> dict[str, Any]:
        name = payload.get('name') or ''
        if not name:
            raise HTTPException(status_code=400, detail='name is required')
        try:
            ws = set_active(name, registry_path)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        audit_record('workspace.activate', workspace=ws.name, params={})
        return asdict(ws)

    @app.delete('/api/workspaces/{name}')
    async def api_remove_workspace(name: str) -> dict[str, Any]:
        ok = remove_workspace(name, registry_path)
        if not ok:
            raise HTTPException(status_code=404, detail='unknown workspace')
        audit_record('workspace.remove', workspace=name, params={})
        return {'removed': name}

    @app.post('/api/validate-path')
    async def api_validate_path(payload: dict[str, str]) -> dict[str, Any]:
        """Check whether a local path exists and is a directory."""
        raw = payload.get('path') or ''
        if not raw:
            raise HTTPException(status_code=400, detail='path is required')
        resolved = Path(raw).expanduser().resolve()
        return {
            'exists': resolved.exists() and resolved.is_dir(),
            'resolved': str(resolved),
            'is_git': (resolved / '.git').exists(),
        }

    _HTTPS_GIT_HOST_RE = re.compile(r'https?://(github|gitlab|bitbucket)\.')

    @app.post('/api/workspaces/clone/preflight')
    async def api_clone_preflight(payload: dict[str, str]) -> dict[str, Any]:
        """Check that a remote git URL is reachable before committing to a full clone.

        Runs ``git ls-remote --exit-code`` with a short timeout and returns
        ``{ok, default_branch}`` so the UI can surface errors immediately.
        """
        url = (payload.get('url') or '').strip()
        if not url:
            raise HTTPException(status_code=400, detail='url is required')
        if not _HTTPS_GIT_HOST_RE.match(url):
            raise HTTPException(
                status_code=400,
                detail='Only HTTPS GitHub, GitLab, or Bitbucket URLs are accepted.',
            )
        try:
            result = subprocess.run(
                ['git', 'ls-remote', '--exit-code', '--symref', url, 'HEAD'],
                capture_output=True,
                text=True,
                timeout=10,
            )
        except subprocess.TimeoutExpired:
            raise HTTPException(status_code=504, detail='Repository did not respond within 10 seconds.')
        except FileNotFoundError:
            raise HTTPException(status_code=500, detail='git not found on this server')

        if result.returncode != 0:
            raise HTTPException(
                status_code=422,
                detail=f'Cannot reach repository: {result.stderr.strip()[:300] or "unknown error"}',
            )

        # Parse default branch from symref output (e.g. "ref: refs/heads/main\tHEAD")
        default_branch = None
        for line in result.stdout.splitlines():
            if line.startswith('ref: refs/heads/'):
                default_branch = line.split('refs/heads/', 1)[1].split('\t')[0].strip()
                break

        return {'ok': True, 'default_branch': default_branch}

    @app.post('/api/workspaces/clone')
    async def api_clone_workspace(payload: dict[str, str]) -> dict[str, Any]:
        """Shallow-clone a remote git URL then register the result as a workspace."""
        import shutil as _shutil

        url = (payload.get('url') or '').strip()
        name = (payload.get('name') or '').strip()
        branch = (payload.get('branch') or '').strip()
        shallow = str(payload.get('shallow', 'true')).lower() != 'false'

        if not url or not name:
            raise HTTPException(status_code=400, detail='url and name are required')

        if not _HTTPS_GIT_HOST_RE.match(url):
            raise HTTPException(
                status_code=400,
                detail='Only HTTPS GitHub, GitLab, or Bitbucket URLs are accepted.',
            )

        clone_root = Path.home() / '.marco' / 'clones'
        clone_root.mkdir(parents=True, exist_ok=True)

        # Normalize name → safe dir name.
        safe_name = ''.join(ch if ch.isalnum() or ch in '-_' else '-' for ch in name).strip('-') or 'workspace'
        dest = clone_root / safe_name
        if dest.exists():
            raise HTTPException(
                status_code=409,
                detail=f'Clone destination already exists: {dest}. Choose a different name.',
            )

        cmd = ['git', 'clone']
        if shallow:
            cmd += ['--depth', '1']
        if branch:
            cmd += ['--branch', branch]
        cmd += ['--', url, str(dest)]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        except subprocess.TimeoutExpired:
            _shutil.rmtree(dest, ignore_errors=True)
            raise HTTPException(status_code=504, detail='git clone timed out after 120 seconds')
        except FileNotFoundError:
            raise HTTPException(status_code=500, detail='git not found on this server')

        if result.returncode != 0:
            _shutil.rmtree(dest, ignore_errors=True)
            raise HTTPException(
                status_code=422,
                detail=f'git clone failed: {result.stderr.strip()[:500]}',
            )

        try:
            ws = add_workspace(safe_name, dest, registry_path)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        audit_record('workspace.clone', workspace=ws.name, params={'url': url, 'dest': ws.path})
        return asdict(ws)

    # ---------- API: read-only repo intel ----------

    @app.get('/api/doctor')
    async def api_doctor() -> dict[str, Any]:
        ws = _require_active_workspace(registry_path)
        try:
            python_version = subprocess.run(['python3', '--version'], capture_output=True, text=True).stdout.strip()
        except FileNotFoundError:
            python_version = 'unavailable'
        return {
            'ok': True,
            'workspace': ws.name,
            'cwd': ws.path,
            'safety_mode': SERVER_PROFILE.safety_mode,
            'pause_before_mutation': SERVER_PROFILE.pause_before_mutation,
            'python_version': python_version,
            'git_available': subprocess.run(['git', '--version'], capture_output=True, text=True).returncode == 0,
        }

    @app.get('/api/status')
    async def api_status() -> dict[str, Any]:
        ws = _require_active_workspace(registry_path)
        root = _workspace_root(ws)
        storage = _storage_for(ws)
        scan = scan_repository(root)
        return {
            'workspace': ws.name,
            'repo': scan.root,
            'file_count': scan.file_count,
            'total_bytes': scan.total_bytes,
            'top_extensions': dict(list(scan.by_extension.items())[:8]),
            'pending_patches': len([p for p in list_patches(storage) if p.status == 'pending']),
            'sessions': len(list_sessions(storage)),
            'safety_mode': SERVER_PROFILE.safety_mode,
        }

    @app.get('/api/inspect')
    async def api_inspect(query: str = '') -> dict[str, Any]:
        ws = _require_active_workspace(registry_path)
        root = _workspace_root(ws)
        return {
            'scan': asdict(scan_repository(root)),
            'architecture': architecture_map(root),
            'config_map': config_map(root),
            'integration_map': integration_map(root),
            'where_edit': where_edit(root, query, limit=10) if query else [],
        }

    @app.get('/api/find')
    async def api_find(pattern: str, limit: int = 50) -> dict[str, Any]:
        ws = _require_active_workspace(registry_path)
        return {'matches': find_files(_workspace_root(ws), pattern, limit=limit)}

    @app.get('/api/lookup')
    async def api_lookup(q: str, limit: int = 50) -> dict[str, Any]:
        ws = _require_active_workspace(registry_path)
        return {'matches': lookup_content(_workspace_root(ws), q, limit=limit)}

    @app.get('/api/routes')
    async def api_routes(limit: int = 100) -> dict[str, Any]:
        ws = _require_active_workspace(registry_path)
        return {'routes': [asdict(r) for r in discover_routes(_workspace_root(ws), limit=limit)]}

    @app.get('/api/env')
    async def api_env(limit: int = 200) -> dict[str, Any]:
        ws = _require_active_workspace(registry_path)
        return {'env_vars': discover_env_vars(_workspace_root(ws), limit=limit)}

    @app.get('/api/scripts')
    async def api_scripts() -> dict[str, Any]:
        ws = _require_active_workspace(registry_path)
        return {'scripts': [asdict(s) for s in discover_scripts(_workspace_root(ws))]}

    @app.get('/api/tree')
    async def api_tree(depth: int = 3) -> dict[str, Any]:
        ws = _require_active_workspace(registry_path)
        return {'lines': render_tree(_workspace_root(ws), max_depth=depth)}

    # ---------- API: memory ----------

    @app.post('/api/memory/{kind}')
    async def api_add_memory(kind: str, payload: dict[str, str]) -> dict[str, Any]:
        if kind not in ('note', 'decision', 'convention'):
            raise HTTPException(status_code=404, detail='unknown memory kind')
        ws = _require_active_workspace(registry_path)
        storage = _storage_for(ws)
        key = payload.get('key') or ''
        topic = payload.get('topic') or ''
        text = payload.get('text') or ''
        if not key or not topic or not text:
            raise HTTPException(status_code=400, detail='key, topic, text are required')
        entry = add_entry(storage, kind=kind, key=key, topic=topic, text=text)
        audit_record(f'memory.add.{kind}', workspace=ws.name, params={'key': key, 'topic': topic})
        return asdict(entry)

    @app.get('/api/memory/{kind}s')
    async def api_list_memory(kind: str, limit: int = 100) -> dict[str, Any]:
        singular = kind.rstrip('s')
        if singular not in ('note', 'decision', 'convention'):
            raise HTTPException(status_code=404, detail='unknown memory kind')
        ws = _require_active_workspace(registry_path)
        storage = _storage_for(ws)
        return {'entries': [asdict(e) for e in list_entries(storage, singular, limit=limit)]}

    # Backwards-compat shims for the pre-refactor routes. Both old and new paths work.
    @app.post('/api/note')
    async def api_add_note_compat(payload: dict[str, str]) -> dict[str, Any]:
        return await api_add_memory('note', payload)

    @app.post('/api/decision')
    async def api_add_decision_compat(payload: dict[str, str]) -> dict[str, Any]:
        return await api_add_memory('decision', payload)

    @app.post('/api/convention')
    async def api_add_convention_compat(payload: dict[str, str]) -> dict[str, Any]:
        return await api_add_memory('convention', payload)

    @app.get('/api/notes')
    async def api_list_notes_compat(limit: int = 100) -> dict[str, Any]:
        return await api_list_memory('notes', limit)

    @app.get('/api/decisions')
    async def api_list_decisions_compat(limit: int = 100) -> dict[str, Any]:
        return await api_list_memory('decisions', limit)

    @app.get('/api/conventions')
    async def api_list_conventions_compat(limit: int = 100) -> dict[str, Any]:
        return await api_list_memory('conventions', limit)

    @app.get('/api/recall')
    async def api_recall(q: str, limit: int = 20) -> dict[str, Any]:
        ws = _require_active_workspace(registry_path)
        storage = _storage_for(ws)
        return {'matches': [asdict(e) for e in recall(storage, q, limit=limit)]}

    # ---------- API: sessions ----------

    @app.get('/api/sessions')
    async def api_sessions() -> dict[str, Any]:
        ws = _require_active_workspace(registry_path)
        storage = _storage_for(ws)
        return {'sessions': [asdict(s) for s in list_sessions(storage)]}

    @app.post('/api/sessions/plan')
    async def api_plan(payload: dict[str, str]) -> dict[str, Any]:
        goal = (payload.get('goal') or '').strip()
        if not goal:
            raise HTTPException(status_code=400, detail='goal is required')
        ws = _require_active_workspace(registry_path)
        storage = _storage_for(ws)
        artifact = create_plan(_workspace_root(ws), storage, goal)
        audit_record('session.plan', workspace=ws.name, params={'goal': goal, 'session_id': artifact.session_id})
        return asdict(artifact)

    @app.post('/api/sessions/{session_id}/execute')
    async def api_execute(session_id: str) -> StreamingResponse:
        ws = _require_active_workspace(registry_path)
        storage = _storage_for(ws)

        def run():
            artifact = execute_plan(storage, session_id)
            audit_record('session.execute', workspace=ws.name, params={'session_id': session_id})
            return asdict(artifact)

        return StreamingResponse(stream_sync_callable(run), media_type='text/event-stream')

    @app.post('/api/sessions/{session_id}/validate')
    async def api_validate(session_id: str) -> StreamingResponse:
        ws = _require_active_workspace(registry_path)
        storage = _storage_for(ws)
        root = _workspace_root(ws)

        def run():
            artifact = validate_session(root, storage, SERVER_PROFILE, session_id)
            audit_record(
                'session.validate',
                workspace=ws.name,
                params={'session_id': session_id, 'status': artifact.status},
            )
            return asdict(artifact)

        return StreamingResponse(stream_sync_callable(run), media_type='text/event-stream')

    @app.post('/api/sessions/{session_id}/recover')
    async def api_recover(session_id: str) -> StreamingResponse:
        ws = _require_active_workspace(registry_path)
        storage = _storage_for(ws)

        def run():
            artifact = recover_session(storage, session_id)
            audit_record('session.recover', workspace=ws.name, params={'session_id': session_id})
            return asdict(artifact)

        return StreamingResponse(stream_sync_callable(run), media_type='text/event-stream')

    @app.get('/api/sessions/{session_id}')
    async def api_session_detail(session_id: str) -> dict[str, Any]:
        ws = _require_active_workspace(registry_path)
        storage = _storage_for(ws)
        try:
            artifact = resume_session(storage, session_id)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail='session not found')
        return asdict(artifact)

    # ---------- API: patches ----------

    @app.get('/api/patches')
    async def api_list_patches() -> dict[str, Any]:
        ws = _require_active_workspace(registry_path)
        storage = _storage_for(ws)
        return {'patches': [asdict(p) for p in list_patches(storage)]}

    @app.post('/api/patches/propose')
    async def api_propose_patch(payload: dict[str, str]) -> dict[str, Any]:
        required = ('name', 'target', 'find', 'replace')
        for key in required:
            if not payload.get(key):
                raise HTTPException(status_code=400, detail=f'{key} is required')
        ws = _require_active_workspace(registry_path)
        storage = _storage_for(ws)
        root = _workspace_root(ws)
        try:
            proposal = propose_patch(
                storage,
                root,
                name=payload['name'],
                target=payload['target'],
                find_text=payload['find'],
                replace_text=payload['replace'],
            )
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        audit_record(
            'patch.propose',
            workspace=ws.name,
            params={'name': payload['name'], 'target': payload['target']},
            patch_id=proposal.patch_id,
        )
        return asdict(proposal)

    @app.get('/api/patches/{patch_id}')
    async def api_show_patch(patch_id: str) -> dict[str, Any]:
        ws = _require_active_workspace(registry_path)
        storage = _storage_for(ws)
        try:
            return asdict(show_patch(storage, patch_id))
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail='patch not found')

    @app.post('/api/patches/{patch_id}/apply')
    async def api_apply_patch(patch_id: str, payload: dict[str, str]) -> dict[str, Any]:
        ws = _require_active_workspace(registry_path)
        storage = _storage_for(ws)
        root = _workspace_root(ws)
        confirm_name = (payload.get('confirm_name') or '').strip()
        try:
            patch = show_patch(storage, patch_id)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail='patch not found')
        if confirm_name != patch.name:
            audit_record(
                'patch.apply.rejected',
                workspace=ws.name,
                params={'reason': 'confirm_name mismatch'},
                patch_id=patch_id,
                result='rejected',
            )
            raise HTTPException(
                status_code=400,
                detail=f'confirm_name must exactly match patch name ({patch.name!r}) to apply.',
            )
        try:
            applied = apply_patch(storage, root, SERVER_PROFILE, patch_id, force=True)
        except (FileNotFoundError, PermissionError, ValueError) as exc:
            audit_record(
                'patch.apply.failed',
                workspace=ws.name,
                params={'error': str(exc)},
                patch_id=patch_id,
                result='failed',
            )
            raise HTTPException(status_code=400, detail=str(exc))
        audit_record('patch.apply', workspace=ws.name, params={'name': patch.name}, patch_id=patch_id)
        return asdict(applied)

    @app.post('/api/patches/{patch_id}/rollback')
    async def api_rollback_patch(patch_id: str) -> dict[str, Any]:
        ws = _require_active_workspace(registry_path)
        storage = _storage_for(ws)
        root = _workspace_root(ws)
        try:
            rolled = rollback_patch(storage, root, patch_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        audit_record('patch.rollback', workspace=ws.name, params={'name': rolled.name}, patch_id=patch_id)
        return asdict(rolled)

    # ---------- API: scaffold ----------

    @app.post('/api/scaffold/{kind}')
    async def api_scaffold(kind: str, payload: dict[str, str]) -> dict[str, Any]:
        name = (payload.get('name') or '').strip()
        if not name:
            raise HTTPException(status_code=400, detail='name is required')
        if kind not in ('page', 'component', 'route', 'service'):
            raise HTTPException(status_code=404, detail='unknown scaffold kind')
        ws = _require_active_workspace(registry_path)
        root = _workspace_root(ws)
        fn = {
            'page': scaffold_page,
            'component': scaffold_component,
            'route': scaffold_route,
            'service': scaffold_service,
        }[kind]
        result = fn(root, name)
        audit_record(f'scaffold.{kind}', workspace=ws.name, params={'name': name, 'path': result.path})
        return asdict(result)

    # ---------- API: scripts ----------

    @app.post('/api/scripts/{script_name}/run')
    async def api_run_script(script_name: str, payload: dict[str, Any]) -> Any:
        ws = _require_active_workspace(registry_path)
        root = _workspace_root(ws)
        scripts = {s.name: s for s in discover_scripts(root)}
        entry = scripts.get(script_name)
        if entry is None:
            raise HTTPException(status_code=404, detail='script not found')

        execute = bool(payload.get('execute'))
        confirm = bool(payload.get('confirm'))

        if not execute:
            return {'dry_run': True, 'command': entry.command}

        if not confirm:
            raise HTTPException(status_code=400, detail='execute=true requires confirm=true')

        if any(token in entry.command for token in SHELL_META):
            raise HTTPException(status_code=400, detail='script contains shell metacharacters')
        parts = shlex.split(entry.command)
        if not parts or parts[0] not in ALLOWED_SCRIPT_PREFIXES:
            raise HTTPException(status_code=400, detail='script prefix is not allowed under workspace-write safety')

        audit_record('script.run', workspace=ws.name, params={'name': script_name, 'command': entry.command})

        async def _stream():
            async for event in stream_subprocess(entry.command, root):
                yield event

        return StreamingResponse(_stream(), media_type='text/event-stream')

    # ---------- API: audit ----------

    @app.get('/api/audit')
    async def api_audit(limit: int = 200) -> dict[str, Any]:
        return {'entries': [asdict(e) for e in audit_tail(limit=limit)]}

    # ---------- Pages: Console ----------

    @app.get('/console', response_class=HTMLResponse)
    async def console_page(request: Request, conversation: str | None = None) -> HTMLResponse:
        ws = _require_active_workspace(registry_path)
        from . import chat_tools

        conversation_id = conversation or 'default'
        path = chat_tools.conversation_path(_workspace_root(ws), conversation_id)
        messages = chat_tools.load_chat_messages(path)
        return templates.TemplateResponse(
            request,
            'console.html',
            _page_context(
                messages=messages,
                conversation_id=conversation_id,
            ),
        )

    # ---------- API: AI (Azure OpenAI / Grok) ----------

    @app.get('/api/ai/status')
    async def api_ai_status() -> dict[str, Any]:
        """Is an LLM provider wired up? Used by UI to enable/disable AI buttons."""
        from . import llm

        configured = llm.is_configured()
        info: dict[str, Any] = {'configured': configured}
        if configured:
            cfg = llm.load_config()
            # Provider-agnostic payload. For legacy clients we also expose a
            # best-effort 'deployment' alias pointing at the active model name.
            info.update({
                'provider': cfg.provider,
                'model': cfg.model,
                'deployment': cfg.model,
                **cfg.display,
            })
        return info

    @app.post('/api/ai/plan')
    async def api_ai_plan(payload: dict[str, str]) -> dict[str, Any]:
        """Turn a goal into a structured plan using Azure OpenAI."""
        from . import llm

        goal = (payload.get('goal') or '').strip()
        if not goal:
            raise HTTPException(status_code=400, detail='goal is required')
        ws = _require_active_workspace(registry_path)
        root = _workspace_root(ws)

        scan = scan_repository(root)
        summary = {
            'workspace': ws.name,
            'file_count': scan.file_count,
            'top_extensions': dict(list(scan.by_extension.items())[:8]),
            'top_dirs': list(scan.top_dirs.keys())[:10],
            'architecture': architecture_map(root),
            'scripts': [s.name for s in discover_scripts(root)][:20],
        }

        try:
            plan = llm.generate_plan(goal, summary)
        except llm.LLMNotConfigured as exc:
            raise HTTPException(status_code=503, detail=str(exc))
        except llm.LLMError as exc:
            raise HTTPException(status_code=502, detail=str(exc))

        # Persist as a Marco session artifact so it shows up on /sessions.
        storage = _storage_for(ws)
        artifact = create_plan(root, storage, goal)
        # Overlay AI plan fields onto the artifact's artifacts dict.
        from .autonomy import SessionArtifact

        enriched = SessionArtifact(
            session_id=artifact.session_id,
            goal=artifact.goal,
            phase=artifact.phase,
            status=artifact.status,
            artifacts={
                **artifact.artifacts,
                'ai_plan': plan,
                'ai_source': 'azure-openai',
            },
            created_at=artifact.created_at,
        )
        storage.write_json(storage.sessions / f'{artifact.session_id}.json', enriched.__dict__)
        audit_record(
            'ai.plan',
            workspace=ws.name,
            params={'goal': goal, 'session_id': artifact.session_id},
        )
        return asdict(enriched)

    @app.post('/api/ai/patch-suggestion')
    async def api_ai_patch_suggestion(payload: dict[str, str]) -> dict[str, Any]:
        """Suggest a patch (name/target/find/replace) from a plain-English description.

        Does NOT apply the patch — returns the suggestion for the user to review,
        and optionally creates a pending patch proposal they can then confirm + apply
        from the normal Patches UI.
        """
        from . import llm

        description = (payload.get('description') or '').strip()
        target = (payload.get('target') or '').strip()
        create_proposal = bool(payload.get('create_proposal', True))
        if not description or not target:
            raise HTTPException(status_code=400, detail='description and target are required')

        ws = _require_active_workspace(registry_path)
        root = _workspace_root(ws)
        target_path = root / target
        if not target_path.exists() or not target_path.is_file():
            raise HTTPException(status_code=400, detail=f'target file does not exist: {target}')

        try:
            contents = target_path.read_text()
        except OSError as exc:
            raise HTTPException(status_code=400, detail=f'could not read target: {exc}')

        try:
            suggestion = llm.suggest_patch(description, target, contents)
        except llm.LLMNotConfigured as exc:
            raise HTTPException(status_code=503, detail=str(exc))
        except llm.LLMError as exc:
            raise HTTPException(status_code=502, detail=str(exc))

        audit_record(
            'ai.patch_suggest',
            workspace=ws.name,
            params={'target': target, 'description': description[:200]},
        )

        result: dict[str, Any] = {'suggestion': suggestion, 'created_proposal': None}

        # Optionally stage it as a pending patch the user can then review + type-confirm.
        if create_proposal and suggestion.get('find') and suggestion.get('replace') is not None:
            storage = _storage_for(ws)
            try:
                proposal = propose_patch(
                    storage,
                    root,
                    name=suggestion.get('name') or 'ai-suggestion',
                    target=target,
                    find_text=suggestion['find'],
                    replace_text=suggestion['replace'],
                )
                audit_record(
                    'patch.propose',
                    workspace=ws.name,
                    params={'name': proposal.name, 'target': target, 'source': 'ai'},
                    patch_id=proposal.patch_id,
                )
                result['created_proposal'] = asdict(proposal)
            except (FileNotFoundError, ValueError) as exc:
                # Don't fail the request — just report the suggestion without a proposal.
                result['proposal_error'] = str(exc)

        return result

    # ---------- API: Chat orchestrator ----------

    CHAT_SYSTEM_PROMPT = (
        'You are Marco, a practical technical operator serving Rudolph. You help him '
        'navigate, understand, and safely modify code repositories.\n\n'
        'You have tools available to inspect the repo, save notes, create session plans, '
        'and stage patches. Use tools whenever they can help; do not guess facts that a '
        'tool can verify.\n\n'
        'Rules:\n'
        '- When the user asks about the repo, prefer calling workspace_status, find_files, '
        'or lookup_content over guessing.\n'
        '- When the user asks to change code, use suggest_patch. The patch will be STAGED '
        'for their review — it will NOT be applied until they type-confirm from the Patches '
        'page. Always tell them where to go to apply it.\n'
        '- When the user says "remember this" or similar, use save_memory.\n'
        '- When the user describes a development goal, use create_plan to stage a structured plan.\n'
        '- Be concise. Prefer bullet points and code blocks over prose.\n'
        '- If a tool returns an error, explain what went wrong and suggest a fix.\n'
        '- Never apply patches, run scripts, or mutate state outside of the provided tools.'
    )

    MAX_CHAT_ITERATIONS = 5

    @app.post('/api/ai/chat')
    async def api_ai_chat(payload: dict[str, Any]) -> StreamingResponse:
        """Single-turn chat with tool calling, streamed as SSE.

        The server runs a short loop: call LLM → if tool_calls, dispatch them →
        feed results back → call LLM again. Max ``MAX_CHAT_ITERATIONS`` rounds.

        SSE events emitted:
          start  {}
          tool   {"name": str, "result": any}   (one per tool call)
          done   assistant message dict
          error  {"message": str}
        """
        from . import chat_tools, llm

        # Validate inputs eagerly (before spawning the thread) so we can still
        # raise a synchronous HTTP error for missing/bad payloads.
        ws = _require_active_workspace(registry_path)
        root = _workspace_root(ws)
        storage = _storage_for(ws)

        message = (payload.get('message') or '').strip()
        if not message:
            raise HTTPException(status_code=400, detail='message is required')
        conversation_id = (payload.get('conversation_id') or 'default').strip() or 'default'
        lite = bool(payload.get('lite'))
        force_heavy = bool(payload.get('force_heavy'))

        try:
            cfg = llm.load_config()
        except llm.LLMNotConfigured as exc:
            raise HTTPException(status_code=503, detail=str(exc))

        # Choose model: lite flag → non-reasoning variant; otherwise full reasoning.
        active_cfg = llm.lite_config(cfg) if lite else cfg

        async def generate() -> AsyncIterator[str]:
            # Light-task gate: emit 'lite' event and let the client decide
            # whether to re-submit with lite=true or force_heavy=true.
            # Only runs when neither flag is set (first, unqualified request).
            if not lite and not force_heavy and _classify_task(message) == 'light':
                yield format_sse('lite', {})
                return

            queue: asyncio.Queue[str | None] = asyncio.Queue()
            loop = asyncio.get_event_loop()

            def emit(event: str, data: Any) -> None:
                loop.call_soon_threadsafe(queue.put_nowait, format_sse(event, data))

            def run() -> None:
                try:
                    chat_path = chat_tools.conversation_path(root, conversation_id)
                    history = chat_tools.load_chat_messages(chat_path)

                    user_msg = {'role': 'user', 'content': message}
                    chat_tools.append_chat_message(chat_path, user_msg)

                    api_messages: list[dict[str, Any]] = [
                        {'role': 'system', 'content': CHAT_SYSTEM_PROMPT}
                    ]
                    for m in history:
                        api_messages.append(m)
                    api_messages.append(user_msg)

                    tool_records: list[dict[str, Any]] = []
                    emit('start', {})

                    for _ in range(MAX_CHAT_ITERATIONS):
                        response = llm.chat_completion(
                            messages=api_messages,
                            tools=chat_tools.TOOL_SCHEMAS,
                            tool_choice='auto',
                            config=active_cfg,
                            max_tokens=4096,
                        )
                        choice = (response.get('choices') or [{}])[0]
                        msg = choice.get('message') or {}
                        tool_calls = msg.get('tool_calls') or []

                        if not tool_calls:
                            final_text = msg.get('content') or ''
                            assistant_msg = {
                                'role': 'assistant',
                                'content': final_text,
                                'tools_used': tool_records,
                            }
                            chat_tools.append_chat_message(chat_path, assistant_msg)
                            audit_record(
                                'chat.turn',
                                workspace=ws.name,
                                params={
                                    'conversation_id': conversation_id,
                                    'tools_used': [r['name'] for r in tool_records],
                                    'tokens': response.get('usage', {}),
                                },
                            )
                            emit('done', assistant_msg)
                            return

                        api_messages.append({
                            'role': 'assistant',
                            'content': msg.get('content'),
                            'tool_calls': tool_calls,
                        })

                        for tc in tool_calls:
                            fn = tc.get('function') or {}
                            tool_name = fn.get('name') or ''
                            raw_args = fn.get('arguments') or '{}'
                            try:
                                parsed_args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                            except Exception:
                                parsed_args = {}

                            result = chat_tools.dispatch_tool(
                                tool_name,
                                parsed_args,
                                root=root,
                                storage=storage,
                                audit=audit_record,
                                workspace_name=ws.name,
                            )
                            tool_records.append({
                                'name': tool_name,
                                'arguments': parsed_args,
                                'result': result,
                            })
                            emit('tool', {'name': tool_name, 'result': result})
                            api_messages.append({
                                'role': 'tool',
                                'tool_call_id': tc.get('id'),
                                'name': tool_name,
                                'content': json.dumps(result)[:16000],
                            })

                    # Exhausted iterations without a final text response.
                    fallback = {
                        'role': 'assistant',
                        'content': (
                            'Reached the tool-call iteration limit without a final answer. '
                            'Tools used: ' + ', '.join(r['name'] for r in tool_records)
                        ),
                        'tools_used': tool_records,
                    }
                    chat_tools.append_chat_message(chat_path, fallback)
                    emit('done', fallback)

                except llm.LLMError as exc:
                    emit('error', {'message': f'LLM error: {exc}'})
                except Exception as exc:  # noqa: BLE001
                    emit('error', {'message': str(exc)})
                finally:
                    loop.call_soon_threadsafe(queue.put_nowait, None)

            t = threading.Thread(target=run, daemon=True)
            t.start()
            while True:
                item = await queue.get()
                if item is None:
                    break
                yield item
            t.join(timeout=5)

        return StreamingResponse(generate(), media_type='text/event-stream')

    @app.get('/api/ai/conversations/{conversation_id}')
    async def api_get_conversation(conversation_id: str) -> dict[str, Any]:
        from . import chat_tools

        ws = _require_active_workspace(registry_path)
        path = chat_tools.conversation_path(_workspace_root(ws), conversation_id)
        return {
            'conversation_id': conversation_id,
            'messages': chat_tools.load_chat_messages(path),
        }

    @app.delete('/api/ai/conversations/{conversation_id}')
    async def api_clear_conversation(conversation_id: str) -> dict[str, Any]:
        from . import chat_tools

        ws = _require_active_workspace(registry_path)
        path = chat_tools.conversation_path(_workspace_root(ws), conversation_id)
        if path.exists():
            path.unlink()
        audit_record('chat.clear', workspace=ws.name, params={'conversation_id': conversation_id})
        return {'cleared': conversation_id}

    # ---------- First-boot bootstrap ----------

    ensure_workspace_from_cwd(registry_path)

    return app


# A module-level app instance so uvicorn can import "src.marco_v3.server:app"
# for ad-hoc dev use. Production entry is `python3 -m src.main serve`.
def _default_app():
    try:
        return create_app()
    except Exception:  # noqa: BLE001
        return None


__all__ = ['create_app', 'format_sse']
