"""Marco UI server — FastAPI wrapper over the v3 CLI.

Single-user operator console. All v3 Python handlers are reused directly;
this module is a thin HTTP + HTML adapter. Deploy target is a single
DigitalOcean Droplet behind Caddy (see ``deploy/``).

The ``MARCO_UI_TOKEN`` env var is required to boot. Every mutation is
recorded to ``~/.marco/audit.log``.
"""

from __future__ import annotations

import shlex
import subprocess
from dataclasses import asdict
from pathlib import Path
from typing import Any

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

    # ---------- API: workspaces ----------

    @app.get('/api/workspaces')
    async def api_list_workspaces() -> dict[str, Any]:
        registry = load_registry(registry_path)
        return {
            'active': registry.active,
            'workspaces': [asdict(ws) for ws in registry.workspaces],
        }

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

    @app.post('/api/{kind}')
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

    @app.get('/api/{kind}s')
    async def api_list_memory(kind: str, limit: int = 100) -> dict[str, Any]:
        singular = kind.rstrip('s')
        if singular not in ('note', 'decision', 'convention'):
            raise HTTPException(status_code=404, detail='unknown memory kind')
        ws = _require_active_workspace(registry_path)
        storage = _storage_for(ws)
        return {'entries': [asdict(e) for e in list_entries(storage, singular, limit=limit)]}

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
