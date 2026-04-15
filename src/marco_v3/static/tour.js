// Marco guided tutorial — dependency-free info cards.
//
// Each step is a page-scoped card explaining *what* a feature is, *when* you'd
// use it, and a *best-practice* tip. Steps may live on different routes; the
// tour hops pages via ?tour=<n> so state survives navigation.

const MARCO_TOUR_KEY = 'marco.tour.v1';

// Active resize/scroll listener reference — tracked so it can be removed on teardown.
let _marcoTourReposition = null;

const TOUR_STEPS = [
  {
    route: '/',
    selector: '#marco-sidebar',
    title: 'Welcome aboard',
    what: 'Marco is your operator companion — he routes plain-language requests to the right tool and keeps every mutation logged.',
    when: 'Any time you would normally SSH in and run a Marco CLI command. The web UI mirrors the CLI, plus adds safety gates and an audit log.',
    best: 'Keep this tour running; each stop covers one page. You can skip anytime (Esc) and relaunch from the sidebar footer or the /help page.',
    placement: 'right',
  },
  {
    route: '/',
    selector: '#marco-workspace-switcher',
    title: 'Workspaces',
    what: 'A workspace is a registered repo on disk. Marco operates on one workspace at a time.',
    when: 'Switch here when you want Marco to target a different repo. Use "+ Add workspace" to register a local path or clone a remote URL.',
    best: 'Local path mode auto-validates the directory and pre-fills the name. Remote URL mode runs a shallow git clone into ~/.marco/clones/.',
    placement: 'right',
  },
  {
    route: '/console',
    selector: '#marco-chat-input',
    title: 'Console — talk to Marco',
    what: 'Plain-language chat. Marco picks the right tool (status, find, lookup, plan, patch-suggest) and reports back.',
    when: 'When you are not sure which CLI command you need, or when the task is light ("show me…", "where do we use…"). The console is not the place for destructive work.',
    best: 'Try: "show me the repo status" · "find all Python files" · "where do we use the database?" Every tool call is logged.',
    placement: 'top',
  },
  {
    route: '/repo',
    selector: 'main',
    title: 'Repo intel',
    what: 'File scan, route discovery, env-var detection, architecture & config maps. Pure read-only.',
    when: 'First stop when onboarding a new workspace — helps you understand what Marco can see.',
    best: 'Use "Where should I edit" to get hints before opening a Patches proposal.',
    placement: 'top',
  },
  {
    route: '/memory',
    selector: 'main',
    title: 'Memory — notes, decisions, conventions',
    what: 'A small structured KV store scoped to the workspace. Three kinds: notes (facts), decisions (why), conventions (house rules).',
    when: 'Record anything you want Marco to recall in future sessions. Use Recall to search across kinds.',
    best: 'Write decisions with a short key ("auth.jwt") and the why in the body. Marco surfaces these in planning prompts.',
    placement: 'top',
  },
  {
    route: '/sessions',
    selector: 'main',
    title: 'Sessions — plan → execute → validate → recover',
    what: 'A four-phase loop for structured work. Plan proposes steps; Execute runs them; Validate confirms; Recover unblocks failures.',
    when: 'Multi-step changes that you want Marco to sequence. Light queries belong in Console.',
    best: 'Always read the plan before executing. If validate fails, Recover generates a targeted fix instead of replanning.',
    placement: 'top',
  },
  {
    route: '/patches',
    selector: 'main',
    title: 'Patches — safe find/replace',
    what: 'Typed find-and-replace proposals. Applying a patch requires typing its name to confirm, and every apply is logged.',
    when: 'Any surgical edit to a single file. Prefer patches over free-form edits so you get a checkpoint and one-click rollback.',
    best: 'Review the diff first. If the find string matches more than once, narrow it until it is unique.',
    placement: 'top',
  },
  {
    route: '/scripts',
    selector: 'main',
    title: 'Scripts — allow-listed runs',
    what: 'Discovered npm / shell scripts. Dry-run by default; execution requires {execute:true, confirm:true}.',
    when: 'Running tests, builds, or lint from the UI without SSH.',
    best: 'Dry-run first to see the expanded command. Only allow-listed prefixes can run — extend ALLOWED_SCRIPT_PREFIXES in config to permit more.',
    placement: 'top',
  },
  {
    route: '/audit',
    selector: 'main',
    title: 'Audit log',
    what: 'Every mutation — memory write, plan, patch apply, script run — lands here with timestamp, workspace, and params.',
    when: 'When something unexpected happened, or when you want proof of what Marco did.',
    best: 'The audit file lives at ~/.marco/audit.log on the Droplet; this view is a tail of the most recent 200.',
    placement: 'top',
  },
  {
    route: '/help',
    selector: 'main',
    title: 'Cheat sheet',
    what: 'A static reference of console phrasings, page purposes, and CLI equivalents. No navigation needed.',
    when: 'When you forget a phrasing or want to see what the CLI counterpart is.',
    best: 'Pin this tab. You can restart this tour from the top of the page.',
    placement: 'top',
  },
];

function marcoTourStart() {
  const url = new URL(window.location.href);
  url.searchParams.set('tour', '0');
  // Jump to the first step's route if we're not on it.
  const first = TOUR_STEPS[0];
  if (window.location.pathname !== first.route) {
    window.location.href = first.route + '?tour=0';
    return;
  }
  _marcoTourShow(0);
}

function _marcoTourShow(index) {
  const step = TOUR_STEPS[index];
  if (!step) { _marcoTourClose('finished'); return; }

  // If the step belongs to a different route, navigate there.
  if (window.location.pathname !== step.route) {
    window.location.href = step.route + '?tour=' + index;
    return;
  }

  _marcoTourTeardown();

  const backdrop = document.createElement('div');
  backdrop.className = 'marco-tour-backdrop';
  backdrop.id = 'marco-tour-backdrop';
  backdrop.addEventListener('click', () => _marcoTourClose('skipped'));
  document.body.appendChild(backdrop);

  const target = document.querySelector(step.selector);
  const highlight = document.createElement('div');
  highlight.className = 'marco-tour-highlight';
  highlight.id = 'marco-tour-highlight';
  document.body.appendChild(highlight);

  const card = document.createElement('div');
  card.className = 'marco-tour-card';
  card.id = 'marco-tour-card';
  card.innerHTML = `
    <button class="marco-tour-close" aria-label="Close tour">&times;</button>
    <div class="marco-tour-step-count">Step ${index + 1} of ${TOUR_STEPS.length}</div>
    <h3>${_marcoEscape(step.title)}</h3>
    <div class="marco-tour-sec"><strong>What</strong>${_marcoEscape(step.what)}</div>
    <div class="marco-tour-sec"><strong>When</strong>${_marcoEscape(step.when)}</div>
    <div class="marco-tour-sec"><strong>Tip</strong>${_marcoEscape(step.best)}</div>
    <div class="marco-tour-controls">
      <button class="marco-tour-secondary" data-act="skip">Skip</button>
      <div class="flex gap-2">
        <button class="marco-tour-secondary" data-act="back" ${index === 0 ? 'disabled style="opacity:0.4;cursor:not-allowed"' : ''}>Back</button>
        <button class="marco-tour-primary" data-act="next">${index === TOUR_STEPS.length - 1 ? 'Finish' : 'Next'}</button>
      </div>
    </div>
  `;
  document.body.appendChild(card);

  card.querySelector('.marco-tour-close').addEventListener('click', () => _marcoTourClose('skipped'));
  card.querySelector('[data-act="skip"]').addEventListener('click', () => _marcoTourClose('skipped'));
  card.querySelector('[data-act="back"]').addEventListener('click', () => { if (index > 0) _marcoTourShow(index - 1); });
  card.querySelector('[data-act="next"]').addEventListener('click', () => _marcoTourShow(index + 1));

  // Remove any previous reposition listener before adding a new one.
  if (_marcoTourReposition) {
    window.removeEventListener('resize', _marcoTourReposition);
    window.removeEventListener('scroll', _marcoTourReposition);
  }
  _marcoTourReposition = () => _marcoTourPosition(target, highlight, card, step.placement);
  _marcoTourReposition();
  window.addEventListener('resize', _marcoTourReposition);
  window.addEventListener('scroll', _marcoTourReposition, { passive: true });

  // Keyboard navigation.
  document.addEventListener('keydown', _marcoTourKey);
}

function _marcoTourKey(ev) {
  if (ev.key === 'Escape') _marcoTourClose('skipped');
  else if (ev.key === 'ArrowRight') document.querySelector('#marco-tour-card [data-act="next"]')?.click();
  else if (ev.key === 'ArrowLeft') document.querySelector('#marco-tour-card [data-act="back"]')?.click();
}

function _marcoTourPosition(target, highlight, card, placement) {
  const pad = 6;
  if (target) {
    const rect = target.getBoundingClientRect();
    highlight.style.top = (rect.top - pad) + 'px';
    highlight.style.left = (rect.left - pad) + 'px';
    highlight.style.width = (rect.width + pad * 2) + 'px';
    highlight.style.height = (rect.height + pad * 2) + 'px';
    highlight.style.display = 'block';

    const cardRect = card.getBoundingClientRect();
    const vh = window.innerHeight;
    const vw = window.innerWidth;
    let top, left;
    if (placement === 'right' && rect.right + 24 + cardRect.width < vw) {
      top = Math.max(16, rect.top);
      left = rect.right + 16;
    } else if (placement === 'top' && rect.top - 24 - cardRect.height > 0) {
      top = rect.top - cardRect.height - 16;
      left = Math.min(vw - cardRect.width - 16, Math.max(16, rect.left));
    } else {
      // Fallback: anchor bottom-right.
      top = vh - cardRect.height - 24;
      left = vw - cardRect.width - 24;
    }
    card.style.top = top + 'px';
    card.style.left = left + 'px';
  } else {
    // No target — center the card.
    highlight.style.display = 'none';
    const cardRect = card.getBoundingClientRect();
    card.style.top = ((window.innerHeight - cardRect.height) / 2) + 'px';
    card.style.left = ((window.innerWidth - cardRect.width) / 2) + 'px';
  }
}

function _marcoTourClose(reason) {
  _marcoTourTeardown();
  if (reason === 'finished' || reason === 'skipped') {
    try { localStorage.setItem(MARCO_TOUR_KEY, reason); } catch (e) { /* quota */ }
  }
  // Clean any lingering ?tour param.
  const url = new URL(window.location.href);
  if (url.searchParams.has('tour')) {
    url.searchParams.delete('tour');
    window.history.replaceState({}, '', url.toString());
  }
}

function _marcoTourTeardown() {
  document.getElementById('marco-tour-backdrop')?.remove();
  document.getElementById('marco-tour-highlight')?.remove();
  document.getElementById('marco-tour-card')?.remove();
  document.removeEventListener('keydown', _marcoTourKey);
  if (_marcoTourReposition) {
    window.removeEventListener('resize', _marcoTourReposition);
    window.removeEventListener('scroll', _marcoTourReposition);
    _marcoTourReposition = null;
  }
}

function _marcoEscape(s) {
  return String(s || '').replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}

// Auto-launch logic on DOMContentLoaded.
document.addEventListener('DOMContentLoaded', () => {
  // Resume if we arrived via ?tour=<n>
  const params = new URLSearchParams(window.location.search);
  if (params.has('tour')) {
    const idx = Number(params.get('tour'));
    // Strip the param but preserve it for _marcoTourShow by removing only after.
    if (!Number.isNaN(idx) && idx >= 0 && idx < TOUR_STEPS.length) {
      // Defer so other DOMContentLoaded listeners (sidebar init) finish first.
      setTimeout(() => _marcoTourShow(idx), 50);
      return;
    }
  }
  // First-visit auto-launch on Dashboard only.
  if (window.location.pathname === '/' && !localStorage.getItem(MARCO_TOUR_KEY)) {
    setTimeout(() => _marcoTourShow(0), 400);
  }
});
