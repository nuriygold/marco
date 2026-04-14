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
          <span class="font-mono text-emerald-300">${escapeHtml(m.key)}</span>
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
