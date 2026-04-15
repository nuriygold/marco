// Marco UI — thin client helpers.
// All mutating actions go through fetch() so we can show confirmation dialogs,
// enforce typed-confirm gates, and wire SSE streams.

async function marcoPost(url, body) {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body || {}),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail.detail || res.statusText);
  }
  return res.json();
}

// ---------- AI (Azure OpenAI) ----------

let _aiStatusCache = null;

async function marcoAIStatus() {
  if (_aiStatusCache) return _aiStatusCache;
  try {
    _aiStatusCache = await marcoGet('/api/ai/status');
  } catch (e) {
    _aiStatusCache = { configured: false };
  }
  return _aiStatusCache;
}

async function marcoInitAIGates() {
  // Disables any button/form with data-ai-gated if Azure OpenAI is not configured,
  // and shows the adjacent #marco-ai-hint / #marco-ai-patch-hint text.
  const status = await marcoAIStatus();
  const gated = document.querySelectorAll('[data-ai-gated="true"]');
  if (!status.configured) {
    gated.forEach(el => { el.disabled = true; });
    const hints = document.querySelectorAll('#marco-ai-hint, #marco-ai-patch-hint');
    hints.forEach(el => el.classList.remove('hidden'));
  }
}

document.addEventListener('DOMContentLoaded', marcoInitAIGates);
document.addEventListener('DOMContentLoaded', marcoSidebarInit);
document.addEventListener('DOMContentLoaded', marcoScrollHelpersInit);

// ---------- Sidebar collapse (desktop icon-rail) ----------

const MARCO_SIDEBAR_KEY = 'marco.sidebar';

function marcoSidebarInit() {
  const aside = document.getElementById('marco-sidebar');
  if (!aside) return;
  if (localStorage.getItem(MARCO_SIDEBAR_KEY) === 'collapsed') {
    aside.classList.add('is-collapsed');
    _marcoSidebarSyncAria(aside, true);
  }
}

function marcoSidebarToggle() {
  const aside = document.getElementById('marco-sidebar');
  if (!aside) return;
  const nowCollapsed = !aside.classList.contains('is-collapsed');
  aside.classList.toggle('is-collapsed', nowCollapsed);
  localStorage.setItem(MARCO_SIDEBAR_KEY, nowCollapsed ? 'collapsed' : 'expanded');
  _marcoSidebarSyncAria(aside, nowCollapsed);
}

function _marcoSidebarSyncAria(aside, collapsed) {
  const btn = aside.querySelector('.marco-sidebar-toggle');
  if (!btn) return;
  btn.setAttribute('aria-expanded', String(!collapsed));
  btn.setAttribute('aria-label', collapsed ? 'Expand sidebar' : 'Collapse sidebar');
  btn.setAttribute('title', collapsed ? 'Expand sidebar' : 'Collapse sidebar');
}

// ---------- Console: floating scroll helpers ----------

function marcoScrollHelpersInit() {
  const transcript = document.getElementById('marco-chat-transcript');
  if (!transcript) return;  // only runs on /console

  const container = document.createElement('div');
  container.className = 'marco-scroll-helpers';
  container.innerHTML = `
    <button type="button" id="marco-scroll-top"
            class="rounded-full bg-hull/95 p-2 text-slate-200 shadow-lg ring-1 ring-slate-700 hover:text-white is-hidden"
            title="Jump to earliest message" aria-label="Jump to earliest message">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="h-5 w-5">
        <polyline points="18 15 12 9 6 15"/>
      </svg>
    </button>
    <button type="button" id="marco-scroll-bottom"
            class="rounded-full bg-hull/95 p-2 text-slate-200 shadow-lg ring-1 ring-slate-700 hover:text-white is-hidden"
            title="Jump to most recent message" aria-label="Jump to most recent message">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="h-5 w-5">
        <polyline points="6 9 12 15 18 9"/>
      </svg>
    </button>
  `;
  document.body.appendChild(container);

  const topBtn = document.getElementById('marco-scroll-top');
  const bottomBtn = document.getElementById('marco-scroll-bottom');

  topBtn.addEventListener('click', () => {
    window.scrollTo({ top: 0, behavior: 'smooth' });
  });
  bottomBtn.addEventListener('click', () => {
    window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' });
  });

  // Show helpers only when there's something to scroll to.
  const update = () => {
    const scrollTop = window.scrollY || document.documentElement.scrollTop;
    const viewport = window.innerHeight;
    const total = document.documentElement.scrollHeight;
    const atTop = scrollTop < 80;
    const atBottom = scrollTop + viewport >= total - 80;
    const scrollable = total > viewport + 40;
    topBtn.classList.toggle('is-hidden', !scrollable || atTop);
    bottomBtn.classList.toggle('is-hidden', !scrollable || atBottom);
  };
  update();
  window.addEventListener('scroll', update, { passive: true });
  window.addEventListener('resize', update);
  // New messages append — re-evaluate.
  new MutationObserver(update).observe(transcript, { childList: true, subtree: true });
}

// ---------- Workspace: add modal ----------

function marcoWorkspaceModalOpen() {
  const modal = document.getElementById('marco-workspace-modal');
  if (!modal) return;
  modal.classList.remove('hidden');
  modal.classList.add('flex');
  document.getElementById('ws-name')?.focus();
  document.addEventListener('keydown', _marcoWsModalKey);
}

function marcoWorkspaceModalClose() {
  const modal = document.getElementById('marco-workspace-modal');
  if (!modal) return;
  modal.classList.add('hidden');
  modal.classList.remove('flex');
  document.removeEventListener('keydown', _marcoWsModalKey);
  // Reset form state.
  document.getElementById('marco-ws-form')?.reset();
  marcoWsModeChange('local');
  const errEl = document.getElementById('ws-error');
  if (errEl) { errEl.classList.add('hidden'); errEl.textContent = ''; }
  const statusEl = document.getElementById('ws-path-status');
  if (statusEl) { statusEl.textContent = ''; }
}

function _marcoWsModalKey(ev) {
  if (ev.key === 'Escape') marcoWorkspaceModalClose();
}

function marcoWsModeChange(mode) {
  const localFields = document.getElementById('ws-local-fields');
  const remoteFields = document.getElementById('ws-remote-fields');
  if (!localFields || !remoteFields) return;
  if (mode === 'local') {
    localFields.classList.remove('hidden');
    remoteFields.classList.add('hidden');
  } else {
    localFields.classList.add('hidden');
    remoteFields.classList.remove('hidden');
  }
}

function marcoWsUpdateCloneDest(url) {
  const hint = document.getElementById('ws-clone-dest-hint');
  if (!hint) return;
  // Extract the last path segment and strip .git suffix.
  const segment = (url.split('/').pop() || '').replace(/\.git$/, '').trim();
  const name = segment || '<name>';
  hint.textContent = `~/.marco/clones/${name}`;
  // Auto-fill the name field if empty.
  const nameInput = document.getElementById('ws-name');
  if (nameInput && !nameInput.value && segment) {
    nameInput.value = segment.replace(/[^a-zA-Z0-9-_]/g, '-').replace(/-+/g, '-').replace(/^-|-$/g, '');
  }
}

async function marcoValidatePath() {
  const pathInput = document.getElementById('ws-path');
  const statusEl = document.getElementById('ws-path-status');
  const path = (pathInput?.value || '').trim();
  if (!path) { statusEl.textContent = '⚠ Enter a path first.'; statusEl.className = 'mt-1 text-xs text-amber-400'; return; }
  statusEl.textContent = 'Checking…'; statusEl.className = 'mt-1 text-xs text-slate-400';
  try {
    const data = await marcoPost('/api/validate-path', { path });
    if (data.exists) {
      const git = data.is_git ? ' · git repo detected' : '';
      statusEl.textContent = `✓ Found${git}`;
      statusEl.className = 'mt-1 text-xs text-rope';
      // Auto-fill name from the last path segment if empty.
      const nameInput = document.getElementById('ws-name');
      if (nameInput && !nameInput.value) {
        nameInput.value = data.resolved.split('/').filter(Boolean).pop() || '';
      }
    } else {
      statusEl.textContent = '✗ Path does not exist or is not a directory.';
      statusEl.className = 'mt-1 text-xs text-red-400';
    }
  } catch (e) {
    statusEl.textContent = '✗ ' + e.message;
    statusEl.className = 'mt-1 text-xs text-red-400';
  }
}

async function marcoWorkspaceSubmit(event) {
  if (event) event.preventDefault();
  const errEl = document.getElementById('ws-error');
  const submitBtn = document.getElementById('ws-submit-btn');
  const hideErr = () => { errEl?.classList.add('hidden'); };
  const showErr = (msg) => {
    if (errEl) { errEl.textContent = msg; errEl.classList.remove('hidden'); }
  };

  const mode = document.querySelector('input[name="ws-mode"]:checked')?.value || 'local';
  const name = (document.getElementById('ws-name')?.value || '').trim();
  if (!name) { showErr('Workspace name is required.'); return false; }

  hideErr();
  submitBtn.disabled = true;
  submitBtn.textContent = mode === 'remote' ? 'Cloning…' : 'Registering…';

  try {
    if (mode === 'local') {
      const path = (document.getElementById('ws-path')?.value || '').trim();
      if (!path) { showErr('Path is required.'); return false; }
      await marcoPost('/api/workspaces', { name, path });
    } else {
      const url = (document.getElementById('ws-url')?.value || '').trim();
      const branch = (document.getElementById('ws-branch')?.value || '').trim();
      const shallow = document.getElementById('ws-shallow')?.checked !== false;
      if (!url) { showErr('Repository URL is required.'); return false; }
      await marcoPost('/api/workspaces/clone', { name, url, branch, shallow: String(shallow) });
    }
    marcoWorkspaceModalClose();
    window.location.reload();
  } catch (e) {
    showErr(e.message || 'Failed to add workspace.');
    submitBtn.disabled = false;
    submitBtn.textContent = 'Add workspace';
  }
  return false;
}

async function marcoRemoveWorkspace(name) {
  if (!name) return;
  if (!confirm(`Remove workspace "${name}" from the registry?\n\nThis does NOT delete any files on disk.`)) return;
  try {
    const res = await fetch(`/api/workspaces/${encodeURIComponent(name)}`, { method: 'DELETE' });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || res.statusText);
    }
    window.location.reload();
  } catch (e) {
    alert('Remove failed: ' + e.message);
  }
}

async function marcoAIPlan(event) {
  if (event) event.preventDefault();
  const input = document.querySelector('input[name="goal"]');
  const goal = (input && input.value || '').trim();
  if (!goal) { alert('Enter a goal first.'); return false; }
  const btn = document.getElementById('marco-ai-plan-btn');
  if (btn) { btn.disabled = true; btn.textContent = '✨ thinking...'; }
  try {
    const session = await marcoPost('/api/ai/plan', { goal });
    window.location.href = `/sessions?focus=${session.session_id}`;
  } catch (e) {
    alert('AI plan failed: ' + e.message);
    if (btn) { btn.disabled = false; btn.textContent = '✨ AI plan'; }
  }
  return false;
}

async function marcoAIPatchSuggest(event) {
  if (event) event.preventDefault();
  const form = document.getElementById('marco-ai-patch-form');
  const description = form.description.value.trim();
  const target = form.target.value.trim();
  if (!description || !target) { alert('Need target + description.'); return false; }
  const btn = document.getElementById('marco-ai-patch-btn');
  if (btn) { btn.disabled = true; btn.textContent = '✨ analyzing...'; }
  try {
    const result = await marcoPost('/api/ai/patch-suggestion', { target, description, create_proposal: true });
    if (result.created_proposal) {
      window.location.href = `/patches/${result.created_proposal.patch_id}`;
    } else {
      alert('Suggestion produced but proposal failed: ' + (result.proposal_error || 'unknown'));
      if (btn) { btn.disabled = false; btn.textContent = '✨ Suggest + stage patch'; }
    }
  } catch (e) {
    alert('AI patch suggestion failed: ' + e.message);
    if (btn) { btn.disabled = false; btn.textContent = '✨ Suggest + stage patch'; }
  }
  return false;
}

// ---------- Console (chat orchestrator) ----------

function marcoChatRenderMessage(msg) {
  const wrap = document.createElement('div');
  wrap.className = 'flex ' + (msg.role === 'user' ? 'justify-end' : 'justify-start');

  const bubble = document.createElement('div');
  bubble.className = 'max-w-[85%] rounded-lg px-3 py-2 text-sm ' + (
    msg.role === 'user' ? 'bg-rope/15 text-foam' :
    msg.role === 'assistant' ? 'bg-slate-800 text-slate-100' :
    'bg-amber-500/10 text-amber-200 text-xs'
  );

  const label = document.createElement('div');
  label.className = 'mb-1 text-[10px] uppercase tracking-wider opacity-60';
  label.textContent = msg.role;
  bubble.appendChild(label);

  const body = document.createElement('div');
  body.className = 'whitespace-pre-wrap';
  body.textContent = msg.content || '';
  bubble.appendChild(body);

  if (msg.tools_used && msg.tools_used.length) {
    const toolsWrap = document.createElement('div');
    toolsWrap.className = 'mt-2 space-y-1';
    msg.tools_used.forEach(t => {
      const d = document.createElement('details');
      d.className = 'rounded bg-slate-950/60 p-2 text-xs';
      const s = document.createElement('summary');
      s.className = 'cursor-pointer font-mono text-beacon';
      s.textContent = '🔧 ' + t.name;
      d.appendChild(s);
      const pre = document.createElement('pre');
      pre.className = 'mt-2 overflow-auto text-[11px] text-slate-400';
      pre.textContent = JSON.stringify(t.result, null, 2);
      d.appendChild(pre);
      toolsWrap.appendChild(d);
    });
    bubble.appendChild(toolsWrap);
  }

  wrap.appendChild(bubble);
  return wrap;
}

// Internal helper — streams /api/ai/chat into an existing assistant bubble.
// extra: optional flags like {lite: true} or {force_heavy: true}.
async function _marcoChatStream(message, convId, bodyEl, toolsEl, statusEl, sendBtn, input, extra) {
  statusEl.classList.remove('hidden');
  sendBtn.disabled = true;
  input.disabled = true;

  // Reset bubble state for re-use (banner → spinner on re-submit).
  bodyEl.className = 'whitespace-pre-wrap';
  bodyEl.textContent = '…';
  toolsEl.innerHTML = '';

  const transcript = document.getElementById('marco-chat-transcript');

  try {
    const res = await fetch('/api/ai/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message,
        conversation_id: convId,
        ...extra,
      }),
    });
    if (!res.ok) {
      const detail = await res.json().catch(() => ({}));
      throw new Error(detail.detail || res.statusText);
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const events = buffer.split('\n\n');
      buffer = events.pop();
      for (const evt of events) {
        const { event: evtName, data } = parseSSE(evt);
        if (evtName === 'lite') {
          // Light task detected — offer fast mode without spending reasoning tokens.
          bodyEl.className = 'text-sm text-slate-300';
          bodyEl.innerHTML =
            'Simple lookup — take my thinking cap off? ' +
            '<button class="ml-2 rounded bg-beacon/30 px-2 py-1 text-xs text-foam hover:bg-beacon/50 focus:outline-none">Yes, go fast</button>' +
            '<button class="ml-1 rounded bg-slate-700 px-2 py-1 text-xs text-slate-300 hover:bg-slate-600 focus:outline-none">No, keep thinking</button>';
          const [yesBtn, noBtn] = bodyEl.querySelectorAll('button');
          yesBtn.onclick = () => _marcoChatStream(message, convId, bodyEl, toolsEl, statusEl, sendBtn, input, { lite: true });
          noBtn.onclick  = () => _marcoChatStream(message, convId, bodyEl, toolsEl, statusEl, sendBtn, input, { force_heavy: true });
          // Re-enable controls while user decides.
          sendBtn.disabled = false;
          input.disabled = false;
          statusEl.classList.add('hidden');
          return;
        } else if (evtName === 'tool') {
          const t = JSON.parse(data);
          const d = document.createElement('details');
          d.className = 'rounded bg-slate-950/60 p-2 text-xs';
          const s = document.createElement('summary');
          s.className = 'cursor-pointer font-mono text-beacon';
          s.textContent = '🔧 ' + t.name;
          d.appendChild(s);
          const pre = document.createElement('pre');
          pre.className = 'mt-2 overflow-auto text-[11px] text-slate-400';
          pre.textContent = JSON.stringify(t.result, null, 2);
          d.appendChild(pre);
          toolsEl.appendChild(d);
        } else if (evtName === 'done') {
          const msg = JSON.parse(data);
          bodyEl.textContent = msg.content || '';
          toolsEl.innerHTML = '';
          (msg.tools_used || []).forEach(t => {
            const d = document.createElement('details');
            d.className = 'rounded bg-slate-950/60 p-2 text-xs';
            const s = document.createElement('summary');
            s.className = 'cursor-pointer font-mono text-beacon';
            s.textContent = '🔧 ' + t.name;
            d.appendChild(s);
            const pre = document.createElement('pre');
            pre.className = 'mt-2 overflow-auto text-[11px] text-slate-400';
            pre.textContent = JSON.stringify(t.result, null, 2);
            d.appendChild(pre);
            toolsEl.appendChild(d);
          });
        } else if (evtName === 'error') {
          const err = JSON.parse(data);
          bodyEl.textContent = 'Error: ' + err.message;
          bodyEl.className += ' text-red-400';
        }
        window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' });
      }
    }
  } catch (e) {
    bodyEl.textContent = 'Error: ' + e.message;
    bodyEl.className += ' text-red-400';
  } finally {
    sendBtn.disabled = false;
    input.disabled = false;
    statusEl.classList.add('hidden');
    input.focus();
  }
}

async function marcoChatSend(event) {
  if (event) event.preventDefault();
  const input = document.getElementById('marco-chat-input');
  const sendBtn = document.getElementById('marco-chat-send');
  const transcript = document.getElementById('marco-chat-transcript');
  const statusEl = document.getElementById('marco-chat-status');

  const message = input.value.trim();
  if (!message) return false;

  const convId = window.MARCO_CONVERSATION_ID || 'default';

  // Echo user message immediately.
  transcript.appendChild(marcoChatRenderMessage({ role: 'user', content: message }));
  window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' });
  input.value = '';

  // Create the assistant bubble once — _marcoChatStream fills it in.
  const assistantWrap = document.createElement('div');
  assistantWrap.className = 'flex justify-start';
  const assistantBubble = document.createElement('div');
  assistantBubble.className = 'max-w-[85%] rounded-lg px-3 py-2 text-sm bg-slate-800 text-slate-100';
  const roleLabel = document.createElement('div');
  roleLabel.className = 'mb-1 text-[10px] uppercase tracking-wider opacity-60';
  roleLabel.textContent = 'assistant';
  const bodyEl = document.createElement('div');
  bodyEl.className = 'whitespace-pre-wrap';
  bodyEl.textContent = '…';
  const toolsEl = document.createElement('div');
  toolsEl.className = 'mt-2 space-y-1';
  assistantBubble.append(roleLabel, bodyEl, toolsEl);
  assistantWrap.appendChild(assistantBubble);
  transcript.appendChild(assistantWrap);
  window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' });

  await _marcoChatStream(message, convId, bodyEl, toolsEl, statusEl, sendBtn, input, {});
  return false;
}

async function marcoClearChat() {
  if (!confirm('Clear this conversation?')) return;
  const id = window.MARCO_CONVERSATION_ID || 'default';
  try {
    await fetch('/api/ai/conversations/' + encodeURIComponent(id), { method: 'DELETE' });
    window.location.reload();
  } catch (e) {
    alert('Clear failed: ' + e.message);
  }
}

async function marcoGet(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(res.statusText);
  return res.json();
}

// ---------- Workspaces ----------

async function marcoAddWorkspace(event) {
  event.preventDefault();
  const form = event.target;
  const body = { name: form.name.value, path: form.path.value };
  try {
    await marcoPost('/api/workspaces', body);
    window.location.reload();
  } catch (e) {
    alert('Failed to add workspace: ' + e.message);
  }
  return false;
}

// ---------- Repo ----------

async function marcoLookup(event, target) {
  event.preventDefault();
  const q = event.target.q.value;
  const out = document.getElementById(target === 'where' ? 'marco-where-output' : 'marco-lookup-output');
  out.textContent = 'searching…';
  try {
    const data = target === 'where'
      ? await marcoGet(`/api/inspect?query=${encodeURIComponent(q)}`)
      : await marcoGet(`/api/lookup?q=${encodeURIComponent(q)}`);
    out.textContent = JSON.stringify(target === 'where' ? data.where_edit : data.matches, null, 2);
  } catch (e) {
    out.textContent = 'error: ' + e.message;
  }
  return false;
}

async function marcoFind(event) {
  event.preventDefault();
  const pattern = event.target.pattern.value;
  const out = document.getElementById('marco-find-output');
  out.textContent = 'searching…';
  try {
    const data = await marcoGet(`/api/find?pattern=${encodeURIComponent(pattern)}`);
    out.textContent = data.matches.join('\n') || '(no matches)';
  } catch (e) {
    out.textContent = 'error: ' + e.message;
  }
  return false;
}

// ---------- Memory ----------

async function marcoAddMemory(event, kind) {
  event.preventDefault();
  const form = event.target;
  const body = { key: form.key.value, topic: form.topic.value, text: form.text.value };
  try {
    await marcoPost(`/api/${kind}`, body);
    window.location.reload();
  } catch (e) {
    alert('Failed to save: ' + e.message);
  }
  return false;
}

async function marcoRecall(event) {
  event.preventDefault();
  const q = event.target.q.value;
  const out = document.getElementById('marco-recall-output');
  out.innerHTML = '<li class="text-slate-500">searching…</li>';
  try {
    const data = await marcoGet(`/api/recall?q=${encodeURIComponent(q)}`);
    if (!data.matches.length) {
      out.innerHTML = '<li class="text-slate-500">no matches</li>';
      return false;
    }
    out.innerHTML = data.matches.map(m => `
      <li class="rounded bg-slate-950 p-2">
        <div class="flex justify-between text-xs">
          <span class="font-mono text-rope">${escapeHtml(m.key)}</span>
          <span class="text-slate-500">${escapeHtml(m.kind)} · ${escapeHtml(m.topic)}</span>
        </div>
        <p class="mt-1 text-xs text-slate-300">${escapeHtml(m.text)}</p>
      </li>`).join('');
  } catch (e) {
    out.innerHTML = `<li class="text-red-400">error: ${escapeHtml(e.message)}</li>`;
  }
  return false;
}

// ---------- Sessions ----------

async function marcoPlan(event) {
  event.preventDefault();
  const goal = event.target.goal.value;
  try {
    await marcoPost('/api/sessions/plan', { goal });
    window.location.reload();
  } catch (e) {
    alert('Failed to plan: ' + e.message);
  }
  return false;
}

function marcoRunSession(id, action) {
  const pane = document.getElementById('marco-session-stream');
  pane.textContent = '';
  streamSSE(`/api/sessions/${id}/${action}`, pane, { method: 'POST' });
}

// ---------- Patches ----------

async function marcoProposePatch(event) {
  event.preventDefault();
  const f = event.target;
  try {
    const proposal = await marcoPost('/api/patches/propose', {
      name: f.name.value,
      target: f.target.value,
      find: f.find.value,
      replace: f.replace.value,
    });
    window.location.href = `/patches/${proposal.patch_id}`;
  } catch (e) {
    alert('Propose failed: ' + e.message);
  }
  return false;
}

function marcoToggleApply(input, expectedName) {
  const btn = document.getElementById('marco-apply-btn');
  btn.disabled = input.value.trim() !== expectedName;
}

async function marcoApplyPatch(event, patchId, expectedName) {
  event.preventDefault();
  const confirmName = event.target.confirm_name.value.trim();
  if (confirmName !== expectedName) {
    alert('Confirm name does not match.');
    return false;
  }
  try {
    await marcoPost(`/api/patches/${patchId}/apply`, { confirm_name: confirmName });
    window.location.reload();
  } catch (e) {
    alert('Apply failed: ' + e.message);
  }
  return false;
}

async function marcoRollbackPatch(patchId) {
  if (!confirm('Rollback this patch? Target file will be restored from the checkpoint.')) return;
  try {
    await marcoPost(`/api/patches/${patchId}/rollback`, {});
    window.location.reload();
  } catch (e) {
    alert('Rollback failed: ' + e.message);
  }
}

// ---------- Scripts ----------

async function marcoRunScript(name, execute) {
  const pane = document.getElementById('marco-script-stream');
  pane.textContent = '';
  if (!execute) {
    try {
      const res = await marcoPost(`/api/scripts/${encodeURIComponent(name)}/run`, { execute: false });
      pane.textContent = `[DRY-RUN] ${res.command}`;
    } catch (e) {
      pane.textContent = 'error: ' + e.message;
    }
    return;
  }
  if (!confirm(`Execute script "${name}"? This will run a real subprocess.`)) return;
  streamSSE(
    `/api/scripts/${encodeURIComponent(name)}/run`,
    pane,
    { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ execute: true, confirm: true }) },
  );
}

// ---------- SSE helper ----------

async function streamSSE(url, pane, init) {
  // The server returns a streaming response; we parse the event-stream manually
  // because fetch with POST cannot use the EventSource API.
  try {
    const res = await fetch(url, init);
    if (!res.ok) {
      const txt = await res.text();
      pane.textContent = `HTTP ${res.status}: ${txt}`;
      return;
    }
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const events = buffer.split('\n\n');
      buffer = events.pop();
      for (const evt of events) {
        const parsed = parseSSE(evt);
        if (parsed.event === 'line') {
          pane.textContent += parsed.data + '\n';
        } else {
          pane.textContent += `[${parsed.event}] ${parsed.data}\n`;
        }
        pane.scrollTop = pane.scrollHeight;
      }
    }
  } catch (e) {
    pane.textContent += `\n[error] ${e.message}`;
  }
}

function parseSSE(block) {
  let event = 'message';
  const data = [];
  for (const line of block.split('\n')) {
    if (line.startsWith('event: ')) event = line.slice(7);
    else if (line.startsWith('data: ')) data.push(line.slice(6));
  }
  return { event, data: data.join('\n') };
}

function escapeHtml(str) {
  return String(str).replace(/[&<>"']/g, s => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[s]));
}
