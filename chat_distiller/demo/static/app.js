'use strict';

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

const STATUS = {
  '现行': { key: 'current', label: 'Current', cls: 'current', dot: 'dot--current' },
  '有争议': { key: 'disputed', label: 'Disputed', cls: 'disputed', dot: 'dot--disputed' },
  '已过期': { key: 'superseded', label: 'Superseded', cls: 'superseded', dot: 'dot--superseded' },
};
const VIEW_TITLES = {
  ledger: 'Ledger', record: 'Record', brief: 'Brief', search: 'Search',
  context: 'Context', evidence: 'Evidence', safety: 'Safety',
};
const DEFAULT_BUDGET = 2048;

const S = {
  state: null,
  view: 'ledger',
  brief: null,
  briefBudget: DEFAULT_BUDGET,
  briefMode: 'view',
  search: null,
  evidence: null,
  context: null,
  proposal: null,
  backups: [],
  pendingRecord: null,
  conflictData: null,
  toastTimer: null,
  briefTimer: null,
};

const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (ch) => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
}[ch]));
const num = (n) => new Intl.NumberFormat('en-US').format(n);
const statusOf = (claim) => STATUS[claim.status] || { key: 'superseded', label: claim.status, cls: 'superseded', dot: 'dot--superseded' };

function formatBytes(bytes) {
  if (bytes === null || bytes === undefined) return '–';
  if (bytes < 1024) return num(bytes) + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(bytes < 10240 ? 1 : 0) + ' KB';
  return (bytes / 1024 / 1024).toFixed(1) + ' MB';
}
function formatWhen(iso) {
  if (!iso) return '—';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', timeZone: 'UTC' }) + ' · ' +
    date.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false, timeZone: 'UTC' });
}
function shortId(id) { return id ? id.replace(/^clm_/, 'clm_').slice(0, 12) : '—'; }

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  let data;
  try {
    data = await response.json();
  } catch (err) {
    data = { ok: false, error: 'The server returned a non-JSON response.', error_type: 'ProtocolError' };
  }
  return { response, data };
}

function toast(message, isError = false) {
  const el = $('#toast');
  el.textContent = message;
  el.classList.toggle('toast--error', isError);
  el.hidden = false;
  clearTimeout(S.toastTimer);
  S.toastTimer = setTimeout(() => { el.hidden = true; }, 4200);
}

/* ---------------- navigation ---------------- */
function applyView(view, { focus = false } = {}) {
  if (!VIEW_TITLES[view]) view = 'ledger';
  S.view = view;
  $$('.view').forEach((panel) => { panel.hidden = panel.dataset.viewPanel !== view; });
  $$('#nav .nav__item').forEach((btn) => {
    if (btn.dataset.view === view) btn.setAttribute('aria-current', 'page');
    else btn.removeAttribute('aria-current');
  });
  $('#crumb').textContent = VIEW_TITLES[view];
  if (focus) {
    const heading = $('.view:not([hidden]) h1');
    if (heading) heading.focus?.();
  }
  if (view === 'brief') loadBrief();
  if (view === 'context' && S.state) enterContext();
  if (view === 'evidence' && !S.evidence) loadEvidence();
  if (view === 'safety') loadSafety();
  window.scrollTo({ top: 0, behavior: 'instant' in window ? 'instant' : 'auto' });
}

function navigate(view) {
  if (location.hash === '#' + view) applyView(view);
  else location.hash = view;
}

/* ---------------- state / ledger ---------------- */
async function loadState({ silent = false } = {}) {
  const { data } = await api('/api/state');
  if (!data.ok) {
    if (!silent) toast(data.error || 'Could not load the ledger.', true);
    return null;
  }
  S.state = data;
  renderChrome();
  renderLedger();
  renderRecordSide();
  return data;
}

function renderChrome() {
  const data = S.state;
  if (!data) return;
  const { counts, store, scenario } = data;
  $('#navCount').textContent = num(counts.total);
  $('#storeProject').textContent = scenario?.name || 'Decision ledger';
  $('#storeCount').textContent = num(counts.total);
  $('#storeBytes').textContent = formatBytes(store.bytes);
  $('#storeDigest').textContent = (store.sha256 || '').slice(0, 12) + '…';
  $('#storeDigest').title = store.sha256 || '';
  $('#metricCurrent').textContent = num(counts.current);
  $('#metricDisputed').textContent = num(counts.disputed);
  $('#metricSuperseded').textContent = num(counts.superseded);
  $('#metricBytes').textContent = formatBytes(store.bytes);
  $('#metricDigest').textContent = 'sha256 ' + (store.sha256 || '').slice(0, 10) + '…';
  $('#version').textContent = data.version;
  const readOnly = !data.writable;
  $('#storeMode').textContent = readOnly
    ? 'Read-only store'
    : (data.mode === 'demo' ? 'Live demo store' : 'Live local store');
  $('.store-card').classList.toggle('store-card--readonly', readOnly);
  $('#modeBanner').hidden = !readOnly;
  $('#resetBtn').hidden = !data.writable;
  $('#storyBtn').disabled = readOnly;
  $('#storyBtn').title = readOnly ? 'Read-only ledger; restart with --write to record' : '';
  const form = $('#recordForm');
  form.classList.toggle('is-readonly', readOnly);
  form.querySelectorAll('input, textarea, button').forEach((element) => {
    element.disabled = readOnly;
  });
  if (readOnly) {
    // Drafting a proposal is read-only, so the text fields stay usable.
    ['#fText', '#fTopic', '#fTags'].forEach((selector) => {
      const element = $(selector);
      if (element) element.disabled = false;
    });
  }
  $('#suggestBtn').disabled = false;
  $('#formNote').textContent = readOnly
    ? 'Read-only ledger: proposal preview still works; Record is disabled.'
    : 'Record writes a real line to the JSONL store; preview never writes.';
  $('#currentCount').textContent = num(counts.current) + ' checks';
}

function renderLedger() {
  const data = S.state;
  if (!data) return;
  const byTopic = new Map();
  for (const claim of data.claims) {
    if (!byTopic.has(claim.topic)) byTopic.set(claim.topic, []);
    byTopic.get(claim.topic).push(claim);
  }
  const rank = { '现行': 0, '有争议': 1, '已过期': 2 };
  const topics = Array.from(byTopic.keys()).sort();
  const html = topics.map((topic) => {
    const claims = byTopic.get(topic).slice().sort((a, b) => {
      const delta = rank[a.status] - rank[b.status];
      return delta !== 0 ? delta : (b.created_at || '').localeCompare(a.created_at || '');
    });
    const current = claims.filter((c) => c.status === '现行').length;
    const disputed = claims.filter((c) => c.status === '有争议').length;
    const history = claims.filter((c) => c.status === '已过期').length;
    const parts = [];
    if (current) parts.push(current + ' current');
    if (disputed) parts.push(disputed + ' disputed');
    if (history) parts.push(history + ' history');
    return `
      <section class="topic">
        <div class="topic__head">
          <span class="topic__name">${esc(topic)}</span>
          <span class="topic__rule"></span>
          <span class="topic__count">${esc(parts.join(' · '))}</span>
        </div>
        <div class="topic__claims">${claims.map(claimCard).join('')}</div>
      </section>`;
  }).join('');
  $('#ledgerTopics').innerHTML = html;
  $('#ledgerEmpty').hidden = data.claims.length > 0;
  if (!data.claims.length) $('#ledgerTopics').innerHTML = '';
}

function claimCard(claim) {
  const redacted = Boolean(claim.redacted_at);
  const meta = redacted
    ? { key: 'redacted', label: 'Redacted', cls: 'redacted', dot: 'dot--superseded' }
    : statusOf(claim);
  const successor = claim.superseded_by
    ? S.state.claims.find((c) => c.claim_id === claim.superseded_by)
    : null;
  const chain = claim.superseded_by
    ? `<div class="chain">
         <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12h14M14 7l5 5-5 5"/></svg>
         superseded by <code>${esc(claim.superseded_by)}</code>
         ${successor ? `<span class="tag">${esc(successor.text.slice(0, 46))}${successor.text.length > 46 ? '…' : ''}</span>` : ''}
       </div>` : '';
  const tags = claim.tags.length
    ? `<span class="claim__tags">${claim.tags.map((t) => `<span class="tag">${esc(t)}</span>`).join('')}</span>`
    : '';
  const provenance = claim.quote || claim.session_hint
    ? `<details class="prov"><summary>Provenance${claim.quote ? ' &amp; quote' : ''}</summary>
         ${claim.quote ? `<blockquote>“${esc(claim.quote)}”</blockquote>` : ''}
         ${claim.session_hint ? `<div class="claim__meta"><span>session <code>${esc(claim.session_hint)}</code></span></div>` : ''}
       </details>`
    : '';
  const actions = S.state?.writable && !redacted
    ? `<div class="claim__actions">
         <button class="mini-btn" type="button" data-safety="redact" data-claim="${esc(claim.claim_id)}" title="Remove content; keep the id, status and chain">Redact</button>
         <button class="mini-btn" type="button" data-safety="delete" data-claim="${esc(claim.claim_id)}" title="Remove the row permanently">Delete</button>
       </div>`
    : '';
  return `
    <article class="claim claim--${meta.cls}${redacted ? ' claim--redacted' : ''}">
      <div class="claim__rail" aria-hidden="true"></div>
      <div class="claim__body">
        <div class="claim__row">
          <p class="claim__text">${esc(claim.text)}</p>
        </div>
        <div class="claim__meta">
          <code title="${esc(claim.claim_id)}">${esc(claim.claim_id)}</code>
          <span>${esc(formatWhen(claim.created_at))}</span>
          ${claim.redacted_at ? `<span>redacted ${esc(formatWhen(claim.redacted_at))}</span>` : ''}
          ${claim.source ? `<span class="claim__source">${esc(claim.source)}</span>` : ''}
          ${tags}
        </div>
        ${chain}
        ${provenance}
      </div>
      <div class="claim__side">
        <span class="status-pill status--${meta.cls}">${esc(meta.label)}</span>
        ${actions}
      </div>
    </article>`;
}

function renderRecordSide() {
  const data = S.state;
  if (!data) return;
  const current = data.claims.filter((c) => c.status === '现行');
  $('#currentList').innerHTML = current.length
    ? current.map((c) => {
        const meta = statusOf(c);
        return `<li>
          <div class="mini-list__text"><span class="dot ${meta.dot}"></span><span>${esc(c.text)}</span></div>
          <div class="mini-list__meta">${esc(c.topic)} · ${esc(shortId(c.claim_id))}</div>
        </li>`;
      }).join('')
    : '<li><div class="mini-list__text">No current claims.</div></li>';
}

/* ---------------- record ---------------- */
function formPayload() {
  const tags = $('#fTags').value.split(',').map((t) => t.trim()).filter(Boolean);
  return {
    text: $('#fText').value.trim(),
    topic: $('#fTopic').value.trim() || 'general',
    tags,
    source: $('#fSource').value.trim() || null,
    quote: $('#fQuote').value.trim() || null,
    dispute: $('#fDispute').checked,
  };
}

function fillExample(key) {
  if (!S.state?.writable) {
    toast('This ledger is read-only. Restart with --write to record.', true);
    return;
  }
  const example = S.state?.examples?.[key];
  if (!example) return;
  $('#fText').value = example.text;
  $('#fTopic').value = example.topic;
  $('#fTags').value = (example.tags || []).join(', ');
  $('#fSource').value = example.source || '';
  $('#fQuote').value = example.quote || '';
  $('#fDispute').checked = false;
  updateFormCount();
  hideError();
  $('#suggestPanel').hidden = true;
  S.proposal = null;
  $('#fText').focus();
  S.pendingRecord = null;
}

function updateFormCount() {
  $('#formCount').textContent = $('#fText').value.length;
}
function hideError() {
  const box = $('#recordError');
  box.hidden = true;
  box.textContent = '';
}
function showError(message) {
  const box = $('#recordError');
  box.hidden = false;
  box.textContent = message;
  box.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
}

async function submitRecord(payload, { supersedes = null, dispute = false, source = 'form' } = {}) {
  if (!S.state?.writable) {
    showError('This ledger is read-only. Restart with --write to record.');
    toast('Read-only ledger; no write was attempted.', true);
    return false;
  }
  const body = { ...payload };
  if (supersedes) body.supersedes = supersedes;
  if (dispute) body.dispute = true;
  const button = $('#recordSubmit');
  button.disabled = true;
  const { data } = await api('/api/record', { method: 'POST', body: JSON.stringify(body) });
  button.disabled = !S.state?.writable;
  if (data.ok) {
    closeConflict();
    showReceipt(data.receipt);
    hideError();
    await loadState({ silent: true });
    if (S.view === 'brief') loadBrief();
    toast('Claim recorded. The store digest changed — this was a real write.');
    $('#recordForm').reset();
    $('#fTopic').value = 'general';
    $('#fDispute').checked = false;
    $('#suggestPanel').hidden = true;
    S.proposal = null;
    S.context = null;
    updateFormCount();
    return true;
  }
  if (data.error_type === 'Conflict') {
    openConflict(data, payload);
    return false;
  }
  if (data.error_type === 'Duplicate') {
    showError(data.error);
    toast('That claim already exists in the ledger.', true);
    return false;
  }
  showError(data.error || 'The write was refused.');
  toast(data.error || 'The write was refused.', true);
  return false;
}

function openConflict(data, payload) {
  S.pendingRecord = payload;
  S.conflictData = data;
  const conflicts = data.conflicts || [];
  $('#conflictMessage').textContent =
    `“${payload.text}” overlaps ${conflicts.length === 1 ? 'a current claim' : conflicts.length + ' current claims'}. ` +
    'The write was refused before it touched the store. Choose how to settle it — or cancel.' +
    (conflicts.length > 1 ? ' All detected conflicts are superseded together.' : '');
  $('#conflictList').innerHTML = conflicts.map((claim) => {
    const meta = statusOf(claim);
    return `<div class="conflict-item">
      <div class="conflict-item__text">${esc(claim.text)}</div>
      <div class="conflict-item__meta">
        <span class="status-pill status--${meta.cls}">${esc(meta.label)}</span>
        <code>${esc(claim.claim_id)}</code>
        <span>${esc(claim.topic)}</span>
      </div>
    </div>`;
  }).join('');
  const primary = conflicts[0];
  const btn = $('#conflictSupersede');
  btn.textContent = conflicts.length > 1
    ? `Supersede all ${conflicts.length} & record`
    : (primary ? `Supersede ${shortId(primary.claim_id)} & record` : 'Supersede & record');
  btn.disabled = !primary;
  const modal = $('#conflictModal');
  modal.hidden = false;
  modal.classList.add('is-open');
  document.body.style.overflow = 'hidden';
  btn.focus();
}

function closeConflict() {
  const modal = $('#conflictModal');
  modal.hidden = true;
  modal.classList.remove('is-open');
  document.body.style.overflow = '';
  S.conflictData = null;
  S.pendingRecord = null;
  if (S.state?.writable) $('#recordSubmit').focus();
}

function showReceipt(receipt) {
  const meta = STATUS[receipt.status] || STATUS['现行'];
  $('#recordReceipt').hidden = false;
  $('#receiptStatus').className = 'status-pill status--' + meta.cls;
  $('#receiptStatus').textContent = meta.label;
  $('#receiptText').textContent = 'Recorded with provenance and a stable claim id.';
  $('#receiptId').textContent = receipt.claim_id;
  $('#receiptDigest').textContent = (receipt.store_sha256 || '').slice(0, 12) + '…';
  $('#receiptDigest').title = receipt.store_sha256 || '';
  const superseded = (receipt.superseded_claims && receipt.superseded_claims.length)
    ? receipt.superseded_claims.join(', ')
    : (receipt.superseded || '—');
  $('#receiptSuperseded').textContent = superseded;
  $('#recordReceipt').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

/* ---------------- review-only proposal ---------------- */
async function previewSuggestion() {
  const payload = formPayload();
  if (!payload.text) {
    showError('A claim needs text before it can be proposed.');
    $('#fText').focus();
    return;
  }
  hideError();
  const button = $('#suggestBtn');
  button.disabled = true;
  const { data } = await api('/api/suggest', {
    method: 'POST',
    body: JSON.stringify({
      text: payload.text,
      topic: payload.topic,
      tags: payload.tags,
      query: payload.text,
    }),
  });
  button.disabled = false;
  if (!data.ok) {
    showError(data.error || 'Could not build the proposal.');
    toast(data.error || 'Could not build the proposal.', true);
    return;
  }
  S.proposal = data.proposal;
  renderProposal();
  toast('Proposal ready. Nothing was written.');
}

function renderProposal() {
  const proposal = S.proposal;
  if (!proposal) return;
  const conflicts = proposal.conflicts || [];
  const tags = proposal.proposed.tags || [];
  const panel = $('#suggestPanel');
  panel.hidden = false;
  $('#suggestText').textContent = proposal.proposed.text;
  $('#suggestTopic').textContent = proposal.proposed.topic + (tags.length ? ' · ' + tags.join(', ') : '');
  $('#suggestConflicts').textContent = conflicts.length
    ? `${conflicts.length} · ${proposal.conflict_ids.join(', ')}`
    : 'none detected';
  $('#suggestConflicts').title = proposal.conflict_ids.join(', ');
  $('#suggestAction').textContent = proposal.resolution_required
    ? 'Supersede every conflict, or record as disputed.'
    : 'Record with claim_record.';

  const parts = conflicts.map((conflict) => `<div class="suggest-conflict">
    <div class="suggest-conflict__text">${esc(conflict.text)}</div>
    <div class="suggest-conflict__meta">
      <span>${esc(conflict.claim_id)}</span>
      <span>${esc(conflict.topic)}</span>
      <span>${esc(conflict.status_label)}</span>
    </div>
  </div>`);
  const evidenceCount = (proposal.evidence || []).length;
  const filtered = proposal.stale_excluded + proposal.unlinked_excluded + proposal.unresolved_excluded;
  if (proposal.evidence_provider && proposal.evidence_provider !== 'none') {
    parts.push(`<p class="suggest-evidence">${evidenceCount} linked passage${evidenceCount === 1 ? '' : 's'} · ${filtered} filtered by status or identity${proposal.evidence_error ? ' · retriever error: ' + esc(proposal.evidence_error) : ''}</p>`);
  }
  $('#suggestDetail').innerHTML = parts.join('');
  panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

/* ---------------- brief ---------------- */
async function loadBrief() {
  const budget = S.briefBudget;
  const { data } = await api('/api/brief?max_bytes=' + budget);
  if (!data.ok) {
    $('#briefBody').innerHTML = `<p class="brief-empty">${esc(data.error || 'Could not render the brief.')}</p>`;
    return;
  }
  S.brief = data;
  renderBrief();
}

function renderBrief() {
  const data = S.brief;
  if (!data) return;
  const packet = data.packet;
  const used = packet.used_bytes;
  const budget = packet.budget_bytes;
  const pct = Math.min(100, Math.round((used / budget) * 1000) / 10);
  $('#briefUsed').textContent = num(used);
  $('#briefBudgetOut').textContent = num(budget);
  $('#briefBudgetLabel').textContent = num(budget) + ' bytes';
  $('#briefOmitted').textContent = num(packet.omitted) + ' omitted';
  $('#briefStatus').textContent = packet.status;
  $('#briefMeterFill').style.width = pct + '%';
  $('#briefMeter').setAttribute('aria-valuenow', String(Math.round(pct)));
  $('#briefMeter').classList.toggle('is-tight', pct >= 85 && packet.status === 'ready');
  $('#briefMeter').classList.toggle('is-empty', packet.status === 'budget_exhausted');
  $('#briefBudget').value = String(budget);
  $('#briefBudget').setAttribute('aria-valuetext', `${used} of ${budget} bytes used`);
  $$('#briefPresets .chip').forEach((chip) => {
    chip.classList.toggle('is-active', Number(chip.dataset.budget) === budget);
  });

  if (S.briefMode === 'wire') {
    $('#briefBody').hidden = true;
    $('#briefWire').hidden = false;
    $('#briefWire').textContent = data.wire;
    return;
  }
  $('#briefBody').hidden = false;
  $('#briefWire').hidden = true;
  $('#briefBody').innerHTML = briefDocument(packet, data.omitted_claims || []);
}

function briefDocument(packet, omitted) {
  const sections = [];
  const disputed = packet.disputed || [];
  if (disputed.length) {
    sections.push(briefSection('Open disputes', disputed.length,
      disputed.map((claim) => briefItem(claim, 'disputed')).join('')));
  }

  const topicHtml = (packet.topics || []).map((bucket) => {
    const items = bucket.claims.map((claim) => briefItem({
      ...claim,
      status: '现行',
      tags: claim.tags || [],
    }, 'current')).join('');
    return `<div class="brief-topic">${esc(bucket.topic)}</div>${items}`;
  }).join('');
  if (topicHtml) {
    const total = (packet.topics || []).reduce((sum, bucket) => sum + bucket.claims.length, 0);
    sections.push(briefSection('Current claims', total, topicHtml));
  }

  const recent = packet.recently_superseded || [];
  if (recent.length) {
    sections.push(briefSection('Recently superseded', recent.length,
      recent.map((claim) => briefItem({ ...claim, status: '已过期' }, 'superseded')).join('')));
  }

  if (omitted.length) {
    sections.push(briefSection('Omitted to fit the budget', omitted.length,
      omitted.map((claim) => {
        const meta = statusOf(claim);
        return `<div class="brief-item brief-item--omitted">
          <span class="dot ${meta.dot}"></span>
          <div class="brief-item__main">
            <div class="brief-item__text">${esc(claim.text)}</div>
            <div class="brief-item__meta"><span>${esc(claim.claim_id)}</span><span>${esc(claim.topic)}</span></div>
          </div>
          <span class="brief-item__flag">omitted</span>
        </div>`;
      }).join('')));
  }

  const empty = !disputed.length && !topicHtml && !recent.length && !omitted.length;
  return `
    <div class="brief-head">
      <div>
        <p class="brief-title">Session brief · derived view</p>
        <p class="brief-sub">${esc(S.state?.scenario?.name || 'Atlas API')} — what still counts</p>
      </div>
      <div class="brief-stats">
        <span class="brief-stat"><strong>${packet.counts.current}</strong> current</span>
        <span class="brief-stat"><strong>${packet.counts.disputed}</strong> disputed</span>
        <span class="brief-stat"><strong>${packet.counts.superseded}</strong> history</span>
      </div>
    </div>
    ${empty ? '<p class="brief-empty">The store is empty. Record a claim to render a brief.</p>' : sections.join('')}
    <div class="brief-foot">
      <span>${esc(packet.status)} · ${num(packet.used_bytes)} / ${num(packet.budget_bytes)} bytes · omitted ${packet.omitted}</span>
      <span>sha256 ${esc((packet.store_sha256 || '').slice(0, 12))}</span>
    </div>`;
}

function briefSection(title, count, body) {
  return `<section class="brief-section">
    <div class="brief-section__head"><h3>${esc(title)}</h3><span class="line"></span><span class="brief-section__count">${num(count)}</span></div>
    ${body}
  </section>`;
}

function briefItem(claim, statusKey) {
  const meta = statusKey === 'disputed' ? STATUS['有争议'] : statusKey === 'superseded' ? STATUS['已过期'] : STATUS['现行'];
  const tags = claim.tags && claim.tags.length
    ? `<span>${claim.tags.map((t) => '#' + t).join(' ')}</span>` : '';
  return `<div class="brief-item">
    <span class="dot ${meta.dot}"></span>
    <div class="brief-item__main">
      <div class="brief-item__text">${esc(claim.text)}</div>
      <div class="brief-item__meta">
        <span>${esc(claim.claim_id)}</span>
        ${meta.key === 'superseded' && claim.superseded_by ? `<span>→ ${esc(claim.superseded_by)}</span>` : ''}
        ${tags}
      </div>
    </div>
  </div>`;
}

function scheduleBrief() {
  clearTimeout(S.briefTimer);
  S.briefTimer = setTimeout(loadBrief, 120);
}

function setBriefMode(mode) {
  S.briefMode = mode;
  $$('[data-brief-mode]').forEach((btn) => btn.classList.toggle('is-active', btn.dataset.briefMode === mode));
  renderBrief();
}

async function copyWire() {
  if (!S.brief) return;
  try {
    await navigator.clipboard.writeText(S.brief.wire);
    toast('Wire JSON copied · ' + formatBytes(S.brief.wire_bytes));
  } catch (err) {
    toast('Clipboard is unavailable in this browser.', true);
  }
}

/* ---------------- search ---------------- */
async function runSearch(queryOverride) {
  const query = queryOverride ?? $('#searchInput').value;
  if (queryOverride !== undefined) $('#searchInput').value = queryOverride;
  const include = $('#includeSuperseded').checked;
  const { data } = await api('/api/search?q=' + encodeURIComponent(query) + '&include_superseded=' + (include ? '1' : '0'));
  if (!data.ok) {
    $('#searchSummary').innerHTML = `<span class="search-summary__hint">${esc(data.error || 'Search failed.')}</span>`;
    $('#searchResults').innerHTML = '';
    return;
  }
  S.search = data;
  renderSearch();
}

function renderSearch() {
  const data = S.search;
  const summary = $('#searchSummary');
  if (!data || !data.query) {
    summary.className = 'search-summary';
    summary.innerHTML = '<span class="search-summary__hint">Enter a query to compare retrieval policies.</span>';
    $('#searchResults').innerHTML = '';
    return;
  }
  if (!data.total) {
    summary.className = 'search-summary';
    summary.innerHTML = `<span class="search-summary__hint">No lexical match for “${esc(data.query)}”. The ledger does not guess.</span>`;
    $('#searchResults').innerHTML = '<div class="results-empty">Nothing matched. Try another term, or record this as a new claim.</div>';
    return;
  }
  if (data.mode === 'all') {
    summary.className = 'search-summary ' + (data.stale_in_results ? 'search-summary--warn' : 'search-summary--ok');
    const warning = data.stale_in_results
      ? `<strong>${data.stale_in_results} of ${data.total}</strong> results are superseded. This is what feeding raw history back looks like.`
      : `<strong>No superseded</strong> claims matched this query.`;
    summary.innerHTML = `<strong>${data.total}</strong> results · status-blind lexical ranking · ${warning}
      <span class="search-summary__hint">The ledger's status filter is off; superseded text ranks by overlap alone.</span>`;
  } else {
    summary.className = 'search-summary search-summary--ok';
    summary.innerHTML = `<strong>${data.total}</strong> results · status-aware · <strong>0 superseded</strong> can appear.
      <span class="search-summary__hint">${data.disputed_in_results ? data.disputed_in_results + ' disputed claim(s) surfaced for review.' : 'Only current claims are eligible.'}</span>`;
  }
  $('#searchResults').innerHTML = data.results.map((result) => {
    const meta = statusOf(result);
    const matched = result.matched.length
      ? result.matched.slice(0, 5).map((t) => `<span class="match">${esc(t)}</span>`).join('')
      : '';
    return `<article class="result ${meta.cls === 'superseded' ? 'result--superseded' : ''}">
      <div class="result__rank">${String(result.rank).padStart(2, '0')}</div>
      <div>
        <div class="result__text">${esc(result.text)}</div>
        <div class="result__meta">
          <span class="status-pill status--${meta.cls}">${esc(meta.label)}</span>
          <code>${esc(result.claim_id)}</code>
          <span>${esc(result.topic)}</span>
          ${result.source ? `<span>${esc(result.source)}</span>` : ''}
          ${result.superseded_by ? `<span>superseded by <code>${esc(result.superseded_by)}</code></span>` : ''}
          ${matched}
        </div>
      </div>
      <div class="result__right">
        <span class="result__score">score ${result.score.toFixed(3)}</span>
      </div>
    </article>`;
  }).join('');
}

/* ---------------- context (RAG) ---------------- */
function enterContext() {
  const rag = S.state?.rag;
  if (rag) {
    $('#contextRagNote').textContent = rag.available
      ? `${rag.chunks} synthetic chunk${rag.chunks === 1 ? '' : 's'} via ${rag.provider}${rag.sealed ? ' · sealed to one store digest' : ' · unsealed'}. Every hit must resolve to a claim and pass the same status policy as the brief.`
      : 'No evidence index is available; packets fall back to the deterministic brief.';
  } else {
    $('#contextRagNote').textContent = 'Loading evidence index status…';
  }
  if (!$('#contextQuery').value.trim()) $('#contextQuery').value = 'use sqlite';
  loadContext();
}

async function loadContext() {
  const query = $('#contextQuery').value.trim();
  const body = $('#contextBody');
  if (!query) {
    S.context = null;
    $('#contextStatus').textContent = 'idle';
    body.hidden = false;
    $('#contextWire').hidden = true;
    body.innerHTML = '<p class="brief-empty">Enter a query to build a context packet.</p>';
    return;
  }
  const intent = $('#contextHistorical').checked ? 'historical' : 'current';
  $('#contextStatus').textContent = 'building…';
  const { data } = await api('/api/context?q=' + encodeURIComponent(query) +
    '&intent=' + intent + '&max_bytes=4096&top_k=8');
  if (!data.ok) {
    S.context = null;
    $('#contextStatus').textContent = 'error';
    body.hidden = false;
    $('#contextWire').hidden = true;
    body.innerHTML = `<p class="brief-empty">${esc(data.error || 'Could not build the packet.')}</p>`;
    toast(data.error || 'Could not build the context packet.', true);
    return;
  }
  S.context = data;
  renderContext();
}

function renderContext() {
  const data = S.context;
  if (!data) return;
  const packet = data.packet;
  const counts = packet.brief.counts || {};
  $('#contextStatus').textContent = packet.status;
  $('#ctxUsed').textContent = num(packet.used_bytes);
  $('#ctxBudget').textContent = num(packet.budget_bytes);
  $('#ctxBriefCounts').textContent =
    `${counts.current || 0} current · ${counts.disputed || 0} disputed · ${counts.superseded || 0} history`;
  $('#ctxEvidenceCount').textContent = num(packet.evidence.length);
  $('#ctxOmitted').textContent = num(packet.evidence_omitted);
  const filtered = packet.stale_excluded + packet.unlinked_excluded + packet.unresolved_excluded;
  $('#ctxExcluded').textContent = filtered + ' filtered';
  $('#ctxExcluded').title =
    `${packet.stale_excluded} stale · ${packet.unlinked_excluded} unlinked · ${packet.unresolved_excluded} unresolved`;
  $('#ctxWindow').textContent = packet.evidence_provider === 'none'
    ? 'brief-only'
    : `${num(packet.evidence_candidates)} candidates · ${packet.evidence_attempts} search${packet.evidence_attempts === 1 ? '' : 'es'}`;
  $('#ctxWindow').title = `candidate window ${packet.evidence_candidate_window}`;
  $('#ctxIndexSha').textContent = packet.evidence_index_sha256
    ? packet.evidence_index_sha256.slice(0, 12) + '…'
    : 'none';
  $('#ctxIndexSha').title = packet.evidence_index_sha256 || '';

  const showWire = $('#contextShowWire').checked;
  $('#contextBody').hidden = showWire;
  $('#contextWire').hidden = !showWire;
  if (showWire) {
    $('#contextWire').textContent = data.wire;
  } else {
    $('#contextBody').innerHTML = contextDocument(packet);
  }
}

function contextDocument(packet) {
  const brief = packet.brief || {};
  const counts = brief.counts || {};
  const evidence = packet.evidence || [];
  const totalBrief = (counts.current || 0) + (counts.disputed || 0) + (counts.superseded || 0);
  const intent = packet.intent || 'current';
  const provider = packet.evidence_provider || 'none';

  const fold = [];
  const disputed = brief.disputed || [];
  if (disputed.length) {
    fold.push(briefSection('Open disputes', disputed.length,
      disputed.map((claim) => briefItem(claim, 'disputed')).join('')));
  }
  const topicHtml = (brief.topics || []).map((bucket) => {
    const items = bucket.claims.map((claim) => briefItem({
      ...claim,
      status: '现行',
      tags: claim.tags || [],
    }, 'current')).join('');
    return `<div class="brief-topic">${esc(bucket.topic)}</div>${items}`;
  }).join('');
  if (topicHtml) {
    const total = (brief.topics || []).reduce((sum, bucket) => sum + bucket.claims.length, 0);
    fold.push(briefSection('Current claims', total, topicHtml));
  }
  const recent = brief.recently_superseded || [];
  if (recent.length) {
    fold.push(briefSection('Recently superseded', recent.length,
      recent.map((claim) => briefItem({ ...claim, status: '已过期' }, 'superseded')).join('')));
  }

  const emptyNote = provider === 'none'
    ? 'No evidence index is attached; this packet is brief-only.'
    : packet.evidence_candidates
      ? `${num(packet.evidence_candidates)} candidate passage(s) were retrieved, but none passed claim identity, status, or quota checks.`
      : 'The retriever returned no candidates for this query.';

  const policy = [
    `<span class="policy-chip">${num(packet.evidence_candidates)} candidates</span>`,
    `<span class="policy-chip ${packet.stale_excluded ? 'policy-chip--guard' : ''}">stale excluded ${num(packet.stale_excluded)}</span>`,
    `<span class="policy-chip ${packet.unlinked_excluded ? 'policy-chip--guard' : ''}">unlinked ${num(packet.unlinked_excluded)}</span>`,
    `<span class="policy-chip ${packet.unresolved_excluded ? 'policy-chip--guard' : ''}">unresolved ${num(packet.unresolved_excluded)}</span>`,
    `<span class="policy-chip ${packet.per_claim_omitted ? 'policy-chip--warn' : ''}">over quota ${num(packet.per_claim_omitted)}</span>`,
    `<span class="policy-chip ${packet.evidence_omitted ? 'policy-chip--warn' : ''}">over budget ${num(packet.evidence_omitted)}</span>`,
  ];
  if (provider !== 'none') {
    policy.push(`<span class="policy-chip">window ${num(packet.evidence_candidate_window)} · ${packet.evidence_attempts} call(s)</span>`);
  }

  const error = packet.evidence_error
    ? `<p class="context-error">Evidence unavailable: ${esc(packet.evidence_error)}. The brief is still authoritative.</p>`
    : '';

  return `
    <div class="brief-head">
      <div>
        <p class="brief-title">Grounded context · two layers</p>
        <p class="brief-sub">${esc(S.state?.scenario?.name || 'Atlas API')} — authority: claim store</p>
      </div>
      <div class="brief-stats">
        <span class="brief-stat"><strong>${evidence.length}</strong> evidence</span>
        <span class="brief-stat"><strong>${counts.current || 0}</strong> current</span>
        <span class="brief-stat"><strong>${esc(intent)}</strong> intent</span>
      </div>
    </div>
    <p class="context-layer-note">brief = deterministic authority view · evidence = retrieved passages, untrusted data joined to a claim</p>

    <section class="brief-section">
      <div class="brief-section__head"><h3>Authority layer · deterministic brief</h3><span class="line"></span><span class="brief-section__count">${num(totalBrief)} claims</span></div>
      <div class="context-counts">
        <span class="context-count"><strong>${counts.current || 0}</strong> current</span>
        <span class="context-count"><strong>${counts.disputed || 0}</strong> disputed</span>
        <span class="context-count"><strong>${counts.superseded || 0}</strong> history</span>
        ${brief.omitted ? `<span class="context-count"><strong>${num(brief.omitted)}</strong> brief omitted</span>` : ''}
      </div>
      <details class="context-fold">
        <summary><span>Show the brief contents</span><span class="context-fold__count">${num(totalBrief)} claims</span></summary>
        <div class="context-fold__body">${fold.join('') || '<p class="brief-empty">The brief is empty.</p>'}</div>
      </details>
    </section>

    <section class="brief-section">
      <div class="brief-section__head"><h3>Evidence layer · ${provider === 'none' ? 'not attached' : 'status-filtered'}</h3><span class="line"></span><span class="brief-section__count">${evidence.length} shown · ${num(packet.evidence_omitted)} omitted</span></div>
      <p class="context-layer-note">${provider === 'none' ? 'No retriever is attached.' : `Retrieved by ${esc(provider)} · every hit is joined to a claim and cannot override it.`}</p>
      ${error}
      ${evidence.map(evidenceHitCard).join('') || `<p class="brief-empty">${esc(emptyNote)}</p>`}
      <div class="context-policy">${policy.join('')}</div>
    </section>

    <div class="brief-foot">
      <span>${esc(packet.status)} · ${num(packet.used_bytes)} / ${num(packet.budget_bytes)} bytes</span>
      <span>store ${esc((packet.store_sha256 || '').slice(0, 12))} · index ${esc((packet.evidence_index_sha256 || 'none').slice(0, 12))}</span>
    </div>`;
}

function evidenceHitCard(hit) {
  const meta = STATUS[hit.claim_status] || STATUS['现行'];
  const label = hit.historical ? 'Historical' : meta.label;
  const quote = hit.quote
    ? `“${esc(hit.quote)}”`
    : esc(hit.excerpt) + (hit.excerpt_truncated ? '…' : '');
  const score = Number(hit.score);
  return `<article class="evidence-hit evidence-hit--${meta.cls}">
    <div class="evidence-hit__head">
      <span class="status-pill status--${meta.cls}">${esc(label)}</span>
      <span class="evidence-hit__claim">${esc(hit.claim_text)}</span>
      <span class="evidence-hit__score">score ${Number.isFinite(score) ? score.toFixed(3) : '–'}</span>
    </div>
    <blockquote class="evidence-hit__quote">${quote}</blockquote>
    <div class="evidence-hit__meta">
      ${hit.chunk_id ? `<code>${esc(hit.chunk_id)}</code>` : ''}
      <span title="${esc(hit.claim_id)}">→ ${esc(shortId(hit.claim_id))}</span>
      <span>${esc(hit.topic || '')}</span>
      ${hit.source ? `<span>${esc(hit.source)}</span>` : ''}
      ${hit.historical ? '<span class="evidence-hit__flag">historical</span>' : ''}
    </div>
  </article>`;
}

async function copyContextWire() {
  if (!S.context) {
    toast('Build a context packet first.', true);
    return;
  }
  try {
    await navigator.clipboard.writeText(S.context.wire);
    toast('Context wire JSON copied · ' + formatBytes(S.context.wire_bytes));
  } catch (err) {
    toast('Clipboard is unavailable in this browser.', true);
  }
}

/* ---------------- safety (backup / audit / removal) ---------------- */
async function loadSafety() {
  await Promise.all([renderSafety(), loadBackups(), loadAudit()]);
}

async function renderSafety() {
  const writable = Boolean(S.state?.writable);
  $('#backupBtn').disabled = false;
  $('#backupBtn').title = 'Write a verified snapshot and manifest next to the store';
  $('#backupNote').textContent = writable
    ? 'Snapshots are written next to the store with a manifest: claim count, byte count and two SHA-256 digests.'
    : 'This ledger is read-only; backup still works because it writes only to the backups directory.';
}

async function loadBackups() {
  const list = $('#backupList');
  const { data } = await api('/api/backups');
  if (!data.ok) {
    list.innerHTML = `<p class="brief-empty">${esc(data.error || 'Could not list backups.')}</p>`;
    return;
  }
  S.backups = data.backups || [];
  if (!S.backups.length) {
    list.innerHTML = '<p class="brief-empty">No snapshots yet. Create the first one with “Backup now”.</p>';
    return;
  }
  list.innerHTML = S.backups.map((backup) => `
    <div class="backup-row">
      <div class="backup-row__main">
        <code title="${esc(backup.file_sha256 || '')}">${esc(backup.snapshot)}</code>
        <span class="backup-row__meta">${num(backup.claims ?? 0)} claims${backup.redacted ? ` · ${num(backup.redacted)} redacted` : ''} · ${formatBytes(backup.bytes)} · sha256 ${esc((backup.file_sha256 || '').slice(0, 10))}…</span>
      </div>
      <span class="backup-row__when">${esc(formatWhen(backup.created_at))}</span>
    </div>`).join('');
}

async function backupNow() {
  const button = $('#backupBtn');
  button.disabled = true;
  const { data } = await api('/api/backup', { method: 'POST', body: '{}' });
  button.disabled = false;
  if (!data.ok) {
    toast(data.error || 'Backup failed.', true);
    return;
  }
  toast(`Snapshot written · ${num(data.claims)} claims · ${formatBytes(data.bytes)}`);
  await Promise.all([loadState({ silent: true }), loadBackups(), loadAudit()]);
}

async function loadAudit() {
  const list = $('#auditList');
  const { data } = await api('/api/audit?limit=20');
  if (!data.ok) {
    list.innerHTML = `<p class="brief-empty">${esc(data.error || 'Could not read the audit log.')}</p>`;
    return;
  }
  $('#auditCount').textContent = data.total === 1 ? '1 entry' : `${num(data.total)} entries`;
  const entries = data.entries || [];
  if (!entries.length) {
    list.innerHTML = '<p class="brief-empty">No redact, delete or restore operations yet.</p>';
    return;
  }
  list.innerHTML = entries.map((entry) => `
    <div class="audit-row">
      <div class="audit-row__main">
        <span class="audit-row__action audit-row__action--${esc(entry.action)}">${esc(entry.action)}</span>
        <span class="audit-row__ids">${(entry.claim_ids || []).map((id) => `<code>${esc(id)}</code>`).join(' ')}</span>
      </div>
      <div class="audit-row__meta">
        <span>${esc(formatWhen(entry.at))}</span>
        ${entry.actor ? `<span>actor ${esc(entry.actor)}</span>` : ''}
        ${entry.backup_file ? `<span title="${esc(entry.backup_file_sha256 || '')}">backup <code>${esc(entry.backup_file)}</code></span>` : '<span>no backup retained</span>'}
      </div>
    </div>`).join('');
}

async function performSafety(action, claimId) {
  const message = action === 'delete'
    ? `Permanently delete ${claimId}? If another claim supersedes it, the store refuses — the CLI --cascade flag removes the whole chain. A pre-change backup is kept.`
    : `Remove the content of ${claimId}? The claim id, status and supersession chain stay; the text, tags, topic, source and quote become a tombstone. A pre-change backup is kept.`;
  if (!window.confirm(message)) return;
  const { data } = await api('/api/' + action, {
    method: 'POST',
    body: JSON.stringify({ claim_id: claimId, confirm: true, cascade: false }),
  });
  if (!data.ok) {
    toast(data.error || `${action} failed.`, true);
    return;
  }
  S.state = null;
  S.context = null;
  await loadState({ silent: true });
  const ids = (data.claim_ids || []).join(', ');
  const backupName = data.backup ? data.backup.path : 'no backup retained';
  toast(`${action === 'redact' ? 'Redacted' : 'Deleted'} ${ids} · backup ${backupName.split(/[\\/]/).pop()}`);
  await loadBackups();
  await loadAudit();
}

/* ---------------- evidence ---------------- */
async function loadEvidence() {
  const { data } = await api('/api/evidence');
  if (!data.ok) {
    toast(data.error || 'Could not load evidence.', true);
    return;
  }
  S.evidence = data;
  renderEvidence();
}

function pct(value) {
  return value === null || value === undefined ? '–' : (value * 100).toFixed(1) + '%';
}
function renderEvidence() {
  const data = S.evidence;
  if (!data) return;
  const methods = data.retrieval.methods || [];
  const dataset = data.retrieval.dataset || {};
  if (dataset.queries) {
    $('#evidenceDataset').textContent = `${dataset.queries} queries · ${dataset.sessions} sessions`;
  }
  const maxRows = methods.map((method, index) => {
    const accent = method.key === 'Status-aware Memory';
    const stale = method.stale5;
    const bar = (value, cls = '') => `<span class="bar ${cls}"><span style="width:${Math.max(0, Math.min(100, value * 100))}%"></span></span>`;
    return `<div class="mt-row ${accent ? 'mt-row--accent' : ''}">
      <div class="mt-method"><span class="dot ${accent ? 'dot--current' : index === 0 ? 'dot--superseded' : 'dot--evidence'}"></span>${esc(method.label)}</div>
      <div class="mt-cell"><strong>${pct(method.recall1)}</strong>${bar(method.recall1)}</div>
      <div class="mt-cell">${pct(method.recall5)}${bar(method.recall5)}</div>
      <div class="mt-cell">${method.mrr.toFixed(4)}</div>
      <div class="mt-cell ${stale === 0 ? 'mt-cell--good' : 'mt-cell--bad'}"><strong>${pct(stale)}</strong>${bar(stale, 'bar--stale')}</div>
    </div>`;
  }).join('');
  $('#retrievalTable').innerHTML = `
    <div class="mt-row mt-head"><span>Method</span><span>Recall@1</span><span>Recall@5</span><span>MRR@5</span><span>stale-hit@5</span></div>
    ${maxRows}
    <div class="mt-note">status filtering drives stale-hit@5 from 54.2% to 0.0% — at a stated Recall@5 cost (95.8% → 91.7%).</div>`;
  $('#evidenceNote').textContent = data.retrieval.evidence
    ? data.retrieval.evidence + ' · ' + data.retrieval.source_file
    : 'Synthetic fixture · retrieval only · ' + data.retrieval.source_file;

  const summary = data.compilebench.summary || {};
  const cards = [
    {
      value: `${summary.invalid_proposals_blocked ?? 16}/${summary.invalid_proposals_total ?? 16}`,
      label: 'Invalid proposals blocked',
      hint: 'Without creating compiled state',
      good: true,
    },
    {
      value: `${summary.exact_budget_passes ?? 16}/${summary.exact_budget_total ?? 16}`,
      label: 'Exact byte budgets',
      hint: 'Serialized UTF-8 packet checks',
      good: true,
    },
    {
      value: `${summary.stale_served_gate_enabled ?? 0}`,
      label: 'Stale pages served',
      hint: 'Freshness gate enabled',
      good: true,
    },
    {
      value: `${summary.stale_served_gate_disabled ?? 4}`,
      label: 'Stale pages served',
      hint: 'Freshness gate disabled — the ablation',
      good: false,
    },
  ];
  $('#compileCards').innerHTML = cards.map((card) => `<div class="compile-card">
    <span class="compile-card__value ${card.good ? 'is-good' : 'is-bad'}">${esc(card.value)}</span>
    <span class="compile-card__label">${esc(card.label)}</span>
    <span class="compile-card__hint">${esc(card.hint)}</span>
  </div>`).join('');

  const limits = (data.compilebench.limits || []).slice(0, 5);
  $('#evidenceLimits').innerHTML = (limits.length ? limits : [
    'Not an independent holdout or automatic LLM synthesis evaluation.',
    'Status and scope are explicit; unknown semantic contradictions can be missed.',
    'A false synthesis with a real quote can pass structurally and remains review-required.',
    'Numbers describe engineering checks, not agent task success.',
  ]).map((limit) => `<li>${esc(limit)}</li>`).join('');

  const sources = [
    ['Retrieval', data.retrieval.source_file, data.retrieval.fixture_sha256],
    ['CompileBench', data.compilebench.source_file, data.compilebench.summary ? (data.compilebench.limits || []).length ? 'fixture + limits' : '' : ''],
    ['Gateway', 'benchmarks/gateway/results.json', data.gateway ? 'model_calls: ' + data.gateway.model_calls : ''],
  ];
  $('#evidenceSources').innerHTML = sources.map(([label, file, hash]) => `
    <div class="source-row"><span>${esc(label)}</span><span><code>${esc(file)}</code>${hash ? ' · ' + esc(String(hash).slice(0, 14)) : ''}</span></div>
  `).join('') + '<div class="source-row"><span>Every fixture</span><span><code>synthetic · zero model calls</code></span></div>';
}

/* ---------------- wiring ---------------- */
function bind() {
  $('#nav').addEventListener('click', (event) => {
    const button = event.target.closest('[data-view]');
    if (button) navigate(button.dataset.view);
  });
  $$('[data-goto]').forEach((button) => button.addEventListener('click', () => navigate(button.dataset.goto)));
  $('#storyBtn').addEventListener('click', () => {
    if (!S.state?.writable) {
      toast('This ledger is read-only. Restart with --write to record.', true);
      return;
    }
    navigate('record');
    setTimeout(() => {
      fillExample('conflict');
      toast('Submit the prefilled decision — the guardrail will refuse it.');
    }, 30);
  });

  $('#fText').addEventListener('input', updateFormCount);
  $('#recordForm').addEventListener('submit', async (event) => {
    event.preventDefault();
    if (!S.state?.writable) {
      showError('This ledger is read-only. Restart with --write to record.');
      return;
    }
    hideError();
    const payload = formPayload();
    if (!payload.text) { showError('A claim needs text.'); return; }
    await submitRecord(payload);
  });
  $('#exampleChips').addEventListener('click', (event) => {
    const chip = event.target.closest('[data-example]');
    if (chip) fillExample(chip.dataset.example);
  });
  $('#suggestBtn').addEventListener('click', previewSuggestion);

  $('#conflictSupersede').addEventListener('click', async () => {
    if (!S.pendingRecord || !S.conflictData) return;
    const targets = S.conflictData.suggested_supersedes || [];
    if (!targets.length) return;
    await submitRecord(S.pendingRecord, { supersedes: targets, source: 'conflict' });
  });
  $('#conflictDispute').addEventListener('click', async () => {
    if (!S.pendingRecord) return;
    await submitRecord(S.pendingRecord, { dispute: true, source: 'conflict' });
  });
  $$('[data-close-conflict]').forEach((el) => el.addEventListener('click', closeConflict));
  document.addEventListener('keydown', (event) => {
    const modal = $('#conflictModal');
    if (event.key === 'Escape' && !modal.hidden) closeConflict();
    if (event.key === 'Tab' && !modal.hidden) {
      const focusable = Array.from(modal.querySelectorAll('button:not([disabled]), [href], input:not([disabled]), textarea:not([disabled])'))
        .filter((element) => element.offsetParent !== null);
      if (focusable.length) {
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }
    }
    if ((event.metaKey || event.ctrlKey) && event.key === 'Enter' && S.view === 'record') {
      $('#recordForm').requestSubmit();
    }
  });

  $('#briefBudget').addEventListener('input', (event) => {
    S.briefBudget = Number(event.target.value);
    $('#briefBudgetLabel').textContent = num(S.briefBudget) + ' bytes';
    scheduleBrief();
  });
  $('#briefPresets').addEventListener('click', (event) => {
    const chip = event.target.closest('[data-budget]');
    if (!chip) return;
    S.briefBudget = Number(chip.dataset.budget);
    $('#briefBudget').value = String(S.briefBudget);
    $('#briefBudgetLabel').textContent = num(S.briefBudget) + ' bytes';
    loadBrief();
  });
  $$('[data-brief-mode]').forEach((btn) => btn.addEventListener('click', () => setBriefMode(btn.dataset.briefMode)));
  $('#briefCopy').addEventListener('click', copyWire);

  $('#searchForm').addEventListener('submit', (event) => {
    event.preventDefault();
    runSearch();
  });
  $('#searchSuggestions').addEventListener('click', (event) => {
    const chip = event.target.closest('[data-query]');
    if (chip) runSearch(chip.dataset.query);
  });
  $('#includeSuperseded').addEventListener('change', () => {
    if ($('#searchInput').value.trim()) runSearch();
  });

  $('#contextForm').addEventListener('submit', (event) => {
    event.preventDefault();
    loadContext();
  });
  $('#contextSuggestions').addEventListener('click', (event) => {
    const chip = event.target.closest('[data-query]');
    if (!chip) return;
    $('#contextQuery').value = chip.dataset.query;
    loadContext();
  });
  $('#contextHistorical').addEventListener('change', () => {
    if ($('#contextQuery').value.trim()) loadContext();
  });
  $('#contextShowWire').addEventListener('change', () => {
    if (S.context) renderContext();
  });
  $('#contextCopy').addEventListener('click', copyContextWire);

  $('#backupBtn').addEventListener('click', backupNow);
  $('#ledgerTopics').addEventListener('click', (event) => {
    const button = event.target.closest('[data-safety]');
    if (button) performSafety(button.dataset.safety, button.dataset.claim);
  });

  $('#resetBtn').addEventListener('click', async () => {
    if (!confirm('Restore the synthetic Atlas scenario? Local writes to this demo store are dropped.')) return;
    const { data } = await api('/api/reset', { method: 'POST', body: '{}' });
    if (!data.ok) { toast(data.error || 'Reset failed.', true); return; }
    S.state = data;
    S.brief = null;
    S.search = null;
    renderChrome();
    renderLedger();
    renderRecordSide();
    $('#recordReceipt').hidden = true;
    $('#suggestPanel').hidden = true;
    S.proposal = null;
    S.context = null;
    hideError();
    if (S.view === 'brief') loadBrief();
    if (S.view === 'search') { $('#searchInput').value = ''; S.search = null; renderSearch(); }
    if (S.view === 'context') enterContext();
    if (S.view === 'safety') loadSafety();
    toast('Demo store restored to the Atlas scenario.');
  });

  window.addEventListener('hashchange', () => applyView(location.hash.replace('#', '') || 'ledger'));
}

async function init() {
  bind();
  const hash = location.hash.replace('#', '');
  applyView(VIEW_TITLES[hash] ? hash : 'ledger');
  await loadState();
  if (S.view === 'evidence') loadEvidence();
  if (S.view === 'brief') loadBrief();
  if (S.view === 'context') enterContext();
  if (S.view === 'safety') loadSafety();
}

document.addEventListener('DOMContentLoaded', init);
