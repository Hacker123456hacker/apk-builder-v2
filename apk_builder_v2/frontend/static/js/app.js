// ============ STATE ============
const state = {
  user: null,
  analysisId: null,
  analysis: null,
  buildType: 'apk',
  currentBuildId: null,
  pollHandle: null,
  fixDone: false,
};

const PHASE_LABELS = {
  fixing: 'Auto-Fixing', uploading: 'Uploading', building: 'Building',
  done: 'Done', error: 'Error',
};
const STATUS_LABELS = {
  queued:'Queued', running:'Building', succeeded:'Build Succeeded',
  failed:'Build Failed', cancelled:'Cancelled', error:'Error',
  creating_repo:'Creating Repo', uploading_files:'Uploading', fixing:'Auto-Fixing',
};
const TERMINAL = new Set(['succeeded','failed','cancelled','error']);

// ============ DOM HELPERS ============
const $ = id => document.getElementById(id);
const show = el => el.classList.remove('hidden');
const hide = el => el.classList.add('hidden');
function toast(msg, dur=2600) {
  const t = $('toast'); t.textContent = msg; show(t);
  setTimeout(() => hide(t), dur);
}
function esc(s) {
  if (!s) return '';
  const d = document.createElement('div'); d.textContent = String(s); return d.innerHTML;
}

// ============ ROUTING ============
function showLoginView() { hide($('view-app')); show($('view-login')); }
function showAppView()   { hide($('view-login')); show($('view-app')); renderTopbarUser(); }

function switchTab(tab) {
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.toggle('active', b.dataset.tab === tab));
  document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
  $(`tab-${tab}`).classList.add('active');
  if (tab === 'history')  loadHistory();
  if (tab === 'settings') renderSettings();
}

// ============ AUTH ============
async function checkSession() {
  const res = await API.me();
  if (res.authenticated) { state.user = res.user; showAppView(); }
  else showLoginView();
}

async function handleConnect() {
  const token = $('pat-input').value.trim();
  const errBox = $('login-error'); hide(errBox);
  if (!token) return;
  const btn = $('connect-btn'); btn.disabled = true; btn.textContent = 'Connecting...';
  try {
    const res = await API.connect(token);
    if (res.success) { state.user = res.user; $('pat-input').value = ''; showAppView(); }
    else { errBox.textContent = res.error || 'Connection failed.'; show(errBox); }
  } catch(e) { errBox.textContent = 'Network error: '+e.message; show(errBox); }
  finally { btn.disabled = false; btn.textContent = 'Connect'; }
}

async function handleLogout() { await API.logout(); state.user = null; showLoginView(); }

function renderTopbarUser() {
  const el = $('topbar-user');
  if (!state.user) { el.innerHTML=''; return; }
  const av = state.user.avatar_url ? `<img src="${esc(state.user.avatar_url)}" alt="">` : '';
  el.innerHTML = `${av}<span class="small">${esc(state.user.login)}</span>`;
}

function renderSettings() {
  const el = $('settings-account');
  if (!state.user) return;
  const av = state.user.avatar_url ? `<img src="${esc(state.user.avatar_url)}" alt="">` : '';
  el.innerHTML = `${av}<div><strong>${esc(state.user.login)}</strong><div class="muted small">@${esc(state.user.login)}</div></div>`;
}

// ============ UPLOAD + ANALYZE ============
function resetUploadStage() {
  state.analysisId = null; state.analysis = null; state.fixDone = false;
  $('validation-card').innerHTML = ''; hide($('validation-card'));
  hide($('fix-panel')); hide($('fix-results-list')); hide($('fix-download-row'));
  hide($('repo-name-field')); hide($('build-type-selector')); hide($('start-build-btn'));
  $('dropzone-text').textContent = 'Click or drag project ZIP here';
}

async function handleFileSelected(file) {
  if (!file || !file.name.endsWith('.zip')) { toast('Please select a .zip file'); return; }
  resetUploadStage();
  $('dropzone-text').textContent = file.name;
  show($('analyzing-indicator'));
  try {
    const result = await API.analyzeZip(file);
    state.analysisId = result.analysis_id; state.analysis = result;
    renderValidationCard(result);
    if (result.is_valid || result.type !== 'unknown') {
      $('repo-name-input').value = result.suggested_repo_name;
      show($('fix-panel'));
      show($('repo-name-field'));
      show($('build-type-selector'));
      show($('start-build-btn'));
    }
  } catch(e) { toast('Error: '+e.message); }
  finally { hide($('analyzing-indicator')); }
}

function renderValidationCard(r) {
  const card = $('validation-card');
  const validIcon = r.is_valid ? '✅' : '⚠️';
  let html = `<div class="validation-head"><span class="type-icon">${r.type_icon}</span><span class="type-label">${esc(r.type_label)}</span><span class="valid-icon">${validIcon}</span></div>`;
  for (const [k,v] of Object.entries(r.detected_info||{}).filter(([k])=>k!=='build_command'))
    html += `<div class="detected-row"><span class="k">${esc(k.replace(/_/g,' '))}:</span><span class="v">${esc(v)}</span></div>`;
  for (const e of r.errors||[]) html += `<div class="issue-line err">✗ ${esc(e)}</div>`;
  for (const w of r.warnings||[]) html += `<div class="issue-line warn">⚠ ${esc(w)}</div>`;
  card.innerHTML = html; show(card);
}

function setBuildType(type) {
  state.buildType = type;
  document.querySelectorAll('.type-chip').forEach(c => c.classList.toggle('active', c.dataset.type === type));
}

// ============ AUTO-FIX ============
async function handleRunFix() {
  const btn = $('run-fix-btn'); btn.disabled = true; btn.textContent = 'Fixing...';
  try {
    const res = await API.runFix(state.analysisId, state.buildType);
    renderFixResults(res.fix_results, $('fix-results-list'));
    show($('fix-results-list'));
    $('fix-summary-text').textContent =
      `${res.total_fixed} fixed / ${res.total_issues} issues found — ${res.critical_count} critical`;
    show($('fix-download-row'));
    state.fixDone = true;
    btn.textContent = '✓ Fixed';
  } catch(e) { toast('Fix error: '+e.message); btn.disabled = false; btn.textContent = 'Run Fixes'; }
}

function renderFixResults(results, container) {
  if (!results || results.length === 0) {
    container.innerHTML = '<div class="muted small" style="padding:6px">No issues found — project looks clean ✓</div>';
    return;
  }
  container.innerHTML = results.map(r => `
    <div class="fix-result-row ${r.severity}">
      <div class="fix-result-header">
        <span class="fix-cat">${esc(r.category)}</span>
        <span class="${r.fixed ? 'fix-status-ok' : 'fix-status-warn'}">${r.fixed ? '✓ Fixed' : '⚠ Manual'}</span>
      </div>
      <div class="fix-issue">${esc(r.issue)}</div>
      ${r.fix ? `<div class="fix-applied">→ ${esc(r.fix)}</div>` : ''}
    </div>
  `).join('');
}

// ============ BUILD ============
async function handleStartBuild() {
  const repoName = $('repo-name-input').value.trim();
  if (!repoName) { toast('Please enter a repository name'); return; }
  const btn = $('start-build-btn'); btn.disabled = true; btn.textContent = 'Starting...';
  try {
    const res = await API.startBuild(state.analysisId, repoName, state.buildType);
    state.currentBuildId = res.build_id;
    enterMonitorStage(repoName);
    startPolling();
  } catch(e) { toast('Error: '+e.message); }
  finally { btn.disabled = false; btn.textContent = '🚀 Start Cloud Build'; }
}

function enterMonitorStage(repoName) {
  hide($('upload-stage')); show($('monitor-stage'));
  $('monitor-repo').textContent = `${state.user.login}/${repoName}`;
  $('steps-list').innerHTML = '';
  $('logs-content').innerHTML = '<div class="logs-empty">Waiting for logs...</div>';
  $('monitor-actions').innerHTML = '';
  hide($('ai-panel'));
  hide($('monitor-fix-summary'));
  updatePhaseUI('fixing');
  updateStatusUI('fixing');
}

// Phase stepper
function updatePhaseUI(phase) {
  ['fixing','uploading','building','done'].forEach(p => {
    const el = $('phase-'+p);
    if (!el) return;
    el.classList.remove('active','done','error');
    const order = ['fixing','uploading','building','done'];
    const cur = order.indexOf(phase);
    const idx = order.indexOf(p);
    if (phase === 'error') {
      if (p !== 'done') el.classList.add('done');
    } else if (idx < cur) el.classList.add('done');
    else if (idx === cur) el.classList.add('active');
  });
}

function updateStatusUI(status) {
  const dot = $('status-dot'), label = $('status-label'), spinner = $('status-spinner');
  dot.className = 'status-dot ' + status;
  label.textContent = STATUS_LABELS[status] || status;
  const inProgress = !TERMINAL.has(status) && status !== 'idle';
  inProgress ? show(spinner) : hide(spinner);
}

function renderSteps(steps) {
  const el = $('steps-list');
  if (!steps || steps.length === 0) { el.innerHTML = ''; return; }
  el.innerHTML = steps.map(step => {
    let cls='', icon='○';
    if (step.status === 'completed') {
      cls = step.conclusion === 'success' ? 'done' : step.conclusion === 'skipped' ? '' : 'failed';
      icon = step.conclusion === 'success' ? '✓' : step.conclusion === 'skipped' ? '–' : '✗';
    } else if (step.status === 'in_progress') { cls = 'running'; icon = '●'; }
    return `<div class="step-row ${cls}"><span class="step-node"></span>${esc(step.name)}</div>`;
  }).join('');
}

function renderLogs(lines) {
  const el = $('logs-content');
  if (!lines || lines.length === 0) {
    el.innerHTML = '<div class="logs-empty">Waiting for logs...</div>'; return;
  }
  el.innerHTML = lines.map(line => {
    let cls = '';
    if (line.startsWith('✅') || line.startsWith('✓')) cls = 'ok';
    else if (line.startsWith('❌') || line.startsWith('✗')) cls = 'err';
    else if (line.startsWith('⚠') || line.startsWith('🔁')) cls = 'warn';
    return `<div class="log-line ${cls}">${esc(line)}</div>`;
  }).join('');
  el.scrollTop = el.scrollHeight;
}

function renderMonitorFixSummary(data) {
  if (!data.fix_results || data.fix_results.length === 0) return;
  const panel = $('monitor-fix-summary');
  $('fix-badge-found').textContent = `${data.issues_found} issues found`;
  $('fix-badge-fixed').textContent = `${data.issues_fixed} auto-fixed`;
  const list = $('monitor-fix-list');
  renderFixResults(data.fix_results, list);
  show(panel);
}

function renderAiPanel(aiAnalysis) {
  if (!aiAnalysis || !aiAnalysis.matched_errors || aiAnalysis.matched_errors.length === 0) return;
  const panel = $('ai-panel');
  $('ai-summary').textContent = aiAnalysis.summary || '';
  $('ai-suggestions').innerHTML = aiAnalysis.matched_errors.map(e => `
    <div class="ai-suggestion-row">
      <div class="ai-suggestion-title">[${esc(e.category)}] ${esc(e.summary)}</div>
      <div class="ai-suggestion-text">💡 ${esc(e.suggestion)}</div>
    </div>
  `).join('');
  show(panel);
}

function renderMonitorActions(data) {
  const el = $('monitor-actions'); el.innerHTML = '';
  if (data.status === 'succeeded') {
    const has = data.artifacts && data.artifacts.length > 0;
    const size = has ? formatBytes(data.artifacts[0].size_in_bytes) : '';
    el.innerHTML = `
      <div class="action-banner success"><span>✅</span><span class="flex1">Build succeeded!</span></div>
      <button class="btn-primary" id="dl-apk-btn" ${has?'':'disabled'}>⬇ Download ${has?data.artifacts[0].name+' ('+size+')':'(no artifact)'}</button>
      <div class="report-btns">
        <button class="btn-outline-small" id="dl-report-html">📋 Fix Report (HTML)</button>
        <button class="btn-outline-small" id="dl-report-json">{ } Fix Report (JSON)</button>
      </div>
    `;
    if (has) $('dl-apk-btn').addEventListener('click', () => { window.location.href = API.getApkDownloadUrl(state.currentBuildId); });
    $('dl-report-html').addEventListener('click', () => window.open(API.getReportHtmlUrl(state.currentBuildId), '_blank'));
    $('dl-report-json').addEventListener('click', () => { window.location.href = API.getReportJsonUrl(state.currentBuildId); });
  } else if (TERMINAL.has(data.status)) {
    el.innerHTML = `
      <div class="action-banner error"><span>⛔</span><span class="flex1">${esc(data.error || 'Build failed. See logs and AI analysis above.')}</span></div>
      ${data.html_url ? `<a class="btn-outline" href="${data.html_url}" target="_blank">View on GitHub ↗</a>` : ''}
      <div class="report-btns">
        <button class="btn-outline-small" id="dl-report-html-f">📋 Fix Report (HTML)</button>
        <button class="btn-outline-small" id="dl-report-json-f">{ } Fix Report (JSON)</button>
      </div>
    `;
    document.getElementById('dl-report-html-f')?.addEventListener('click', () => window.open(API.getReportHtmlUrl(state.currentBuildId), '_blank'));
    document.getElementById('dl-report-json-f')?.addEventListener('click', () => { window.location.href = API.getReportJsonUrl(state.currentBuildId); });
  }
}

function startPolling() {
  if (state.pollHandle) clearInterval(state.pollHandle);
  const poll = async () => {
    try {
      const data = await API.getBuildStatus(state.currentBuildId);
      updatePhaseUI(data.phase || 'fixing');
      updateStatusUI(data.status || data.phase);
      renderSteps(data.steps);
      renderLogs(data.log_lines);
      renderMonitorFixSummary(data);

      if (data.upload_label) {
        show($('upload-progress-wrap'));
        $('upload-progress-bar').style.width = `${(data.upload_progress||0)*100}%`;
        $('upload-progress-label').textContent = data.upload_label;
      } else hide($('upload-progress-wrap'));

      if (data.ai_analysis) renderAiPanel(data.ai_analysis);

      if (TERMINAL.has(data.status)) {
        renderMonitorActions(data);
        clearInterval(state.pollHandle); state.pollHandle = null;
      }
    } catch(e) { console.error('Poll error', e); }
  };
  poll();
  state.pollHandle = setInterval(poll, 3000);
}

function handleNewBuild() {
  if (state.pollHandle) { clearInterval(state.pollHandle); state.pollHandle = null; }
  state.currentBuildId = null;
  resetUploadStage();
  hide($('monitor-stage')); show($('upload-stage'));
  $('file-input').value = '';
}

// ============ HISTORY ============
async function loadHistory() {
  const list = $('history-list'), empty = $('history-empty');
  list.innerHTML = '';
  try {
    const items = await API.getHistory();
    if (!items.length) { show(empty); return; }
    hide(empty);
    list.innerHTML = items.map(renderHistoryCard).join('');
    items.forEach(item => {
      document.querySelector(`[data-dl-apk="${item.id}"]`)?.addEventListener('click', () => { window.location.href = API.getApkDownloadUrl(item.id); });
      document.querySelector(`[data-report-html="${item.id}"]`)?.addEventListener('click', () => window.open(API.getReportHtmlUrl(item.id), '_blank'));
      document.querySelector(`[data-report-json="${item.id}"]`)?.addEventListener('click', () => { window.location.href = API.getReportJsonUrl(item.id); });
      document.querySelector(`[data-del="${item.id}"]`)?.addEventListener('click', () => confirmDel(item.id));
    });
  } catch(e) { toast('Failed to load history'); }
}

function renderHistoryCard(item) {
  const statusText = STATUS_LABELS[item.status] || item.status;
  const started = item.started_at ? new Date(item.started_at).toLocaleString() : '';
  let dur = '';
  if (item.started_at && item.finished_at) {
    const s = Math.round((new Date(item.finished_at) - new Date(item.started_at))/1000);
    dur = ` · ${Math.floor(s/60)}m ${s%60}s`;
  }
  const fixBadge = item.issues_found > 0 ? `<span class="fix-badge green">${item.issues_fixed}/${item.issues_found} fixed</span>` : '';
  return `
    <div class="history-card">
      <div class="history-card-top">
        <strong>${esc(item.project_name)}</strong>
        <span class="status-pill ${item.status}">${esc(statusText)}</span>
      </div>
      <div class="history-meta">${esc(item.project_type)} · ${item.build_type.toUpperCase()} · ${esc(item.repo_full_name)}</div>
      <div class="history-meta">${started}${dur} ${fixBadge}</div>
      <div class="history-actions">
        ${item.has_artifact ? `<button class="btn-small" data-dl-apk="${item.id}">⬇ APK</button>` : ''}
        ${item.html_url ? `<a class="btn-small" href="${item.html_url}" target="_blank">GitHub</a>` : ''}
        <button class="btn-small" data-report-html="${item.id}">📋 Report</button>
        <button class="btn-small" data-report-json="${item.id}">JSON</button>
        <button class="btn-small" data-del="${item.id}">Delete</button>
      </div>
    </div>
  `;
}

function confirmDel(id) {
  showConfirm('Delete build record?', 'Removes from history. GitHub repo is not affected.', 'Delete', async () => {
    await API.deleteHistoryItem(id); loadHistory();
  });
}

// ============ CONFIRM DIALOG ============
function showConfirm(title, body, ok, onOk) {
  $('confirm-title').textContent = title;
  $('confirm-body').textContent = body;
  $('confirm-ok').textContent = ok;
  show($('confirm-dialog'));
  const cleanup = () => { hide($('confirm-dialog')); $('confirm-ok').removeEventListener('click', doOk); $('confirm-cancel').removeEventListener('click', cleanup); };
  const doOk = () => { cleanup(); onOk(); };
  $('confirm-ok').addEventListener('click', doOk);
  $('confirm-cancel').addEventListener('click', cleanup);
}

// ============ UTILS ============
function formatBytes(n) {
  if (!n) return '0 B';
  if (n < 1024) return `${n} B`;
  if (n < 1024*1024) return `${(n/1024).toFixed(1)} KB`;
  return `${(n/(1024*1024)).toFixed(1)} MB`;
}

// ============ WIRE UP ============
document.addEventListener('DOMContentLoaded', () => {
  $('connect-btn').addEventListener('click', handleConnect);
  $('pat-input').addEventListener('keydown', e => { if(e.key==='Enter') handleConnect(); });
  $('toggle-pat').addEventListener('click', () => {
    const i=$('pat-input'); i.type = i.type==='password'?'text':'password';
  });

  document.querySelectorAll('.tab-btn').forEach(b => b.addEventListener('click', () => switchTab(b.dataset.tab)));

  const dropzone=$('dropzone'), fi=$('file-input');
  dropzone.addEventListener('click', () => fi.click());
  fi.addEventListener('change', e => handleFileSelected(e.target.files[0]));
  dropzone.addEventListener('dragover', e => { e.preventDefault(); dropzone.classList.add('dragover'); });
  dropzone.addEventListener('dragleave', () => dropzone.classList.remove('dragover'));
  dropzone.addEventListener('drop', e => { e.preventDefault(); dropzone.classList.remove('dragover'); if(e.dataTransfer.files.length) handleFileSelected(e.dataTransfer.files[0]); });

  $('run-fix-btn').addEventListener('click', handleRunFix);
  $('download-fixed-zip-btn').addEventListener('click', () => { window.location.href = API.getFixedZipUrl(state.analysisId); });

  document.querySelectorAll('.type-chip').forEach(c => c.addEventListener('click', () => setBuildType(c.dataset.type)));
  $('start-build-btn').addEventListener('click', handleStartBuild);
  $('new-build-btn').addEventListener('click', handleNewBuild);
  $('clear-logs-btn').addEventListener('click', () => { $('logs-content').innerHTML = '<div class="logs-empty">Logs cleared.</div>'; });
  $('clear-history-btn').addEventListener('click', () => showConfirm('Clear all history?', 'Build records removed from this server. GitHub repos not affected.', 'Clear', async () => { await API.clearHistory(); loadHistory(); }));
  $('logout-btn').addEventListener('click', () => showConfirm('Disconnect GitHub?', 'Token removed from server.', 'Disconnect', handleLogout));
  $('view-profile-btn').addEventListener('click', () => { if(state.user) window.open(`https://github.com/${state.user.login}`, '_blank'); });

  checkSession();
});
