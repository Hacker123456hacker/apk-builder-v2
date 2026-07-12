const API = {
  async connect(token) {
    const res = await fetch('/api/auth/connect', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({token}) });
    return res.json();
  },
  async me() { return (await fetch('/api/auth/me')).json(); },
  async logout() { return (await fetch('/api/auth/logout', {method:'POST'})).json(); },

  async analyzeZip(file) {
    const fd = new FormData(); fd.append('file', file);
    const res = await fetch('/api/build/analyze', {method:'POST', body:fd});
    if (!res.ok) { const e = await res.json().catch(()=>({})); throw new Error(e.detail||'Upload failed'); }
    return res.json();
  },

  async runFix(analysisId, buildType='apk') {
    const fd = new FormData(); fd.append('build_type', buildType);
    const res = await fetch(`/api/build/fix/${analysisId}`, {method:'POST', body:fd});
    if (!res.ok) { const e = await res.json().catch(()=>({})); throw new Error(e.detail||'Fix failed'); }
    return res.json();
  },

  getFixedZipUrl(analysisId) { return `/api/build/download-fixed/${analysisId}`; },

  async startBuild(analysisId, repoName, buildType) {
    const fd = new FormData();
    fd.append('analysis_id', analysisId);
    fd.append('repo_name', repoName);
    fd.append('build_type', buildType);
    const res = await fetch('/api/build/start', {method:'POST', body:fd});
    if (!res.ok) { const e = await res.json().catch(()=>({})); throw new Error(e.detail||'Start failed'); }
    return res.json();
  },

  async getBuildStatus(buildId) {
    const res = await fetch(`/api/build/status/${buildId}`);
    if (!res.ok) throw new Error('Status fetch failed');
    return res.json();
  },

  getApkDownloadUrl(buildId) { return `/api/build/download/${buildId}`; },
  getReportHtmlUrl(buildId)  { return `/api/build/report/${buildId}/html`; },
  getReportJsonUrl(buildId)  { return `/api/build/report/${buildId}/json`; },

  async getHistory() { return (await fetch('/api/build/history')).json(); },
  async deleteHistoryItem(id) { return (await fetch(`/api/build/history/${id}`, {method:'DELETE'})).json(); },
  async clearHistory() { return (await fetch('/api/build/history', {method:'DELETE'})).json(); },
};
