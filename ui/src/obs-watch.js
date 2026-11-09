/**
 * OBS / network recording folder watcher UI.
 * Backend: /watch/*  — polls a shared folder for finished recordings.
 */
(function () {
  'use strict';

  let pollTimer = null;
  let pollBusy = false;
  let watching = false;

  function statusEl() {
    return document.getElementById('obs-watch-status');
  }

  function setStatus(text) {
    const el = statusEl();
    if (el) el.textContent = text;
  }

  function fmtBytes(n) {
    n = Number(n) || 0;
    if (n < 1024) return n + ' B';
    if (n < 1048576) return (n / 1024).toFixed(1) + ' KB';
    if (n < 1073741824) return (n / 1048576).toFixed(1) + ' MB';
    return (n / 1073741824).toFixed(2) + ' GB';
  }

  function fmtRate(bps) {
    bps = Number(bps) || 0;
    if (bps < 1024) return '';
    return ' · ' + (bps / 1048576).toFixed(1) + ' MB/s';
  }

  async function api(path, opts) {
    const res = await fetch(`${serverUrl}/watch${path}`, opts);
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const detail = typeof data.detail === 'string' ? data.detail : (data.detail && JSON.stringify(data.detail)) || 'Request failed';
      throw new Error(detail);
    }
    return data;
  }

  async function saveConfig(extra) {
    const folder = (document.getElementById('obs-watch-folder')?.value || '').trim();
    const settle = parseFloat(document.getElementById('obs-watch-settle')?.value) || 45;
    const body = Object.assign({
      folder: folder,
      settle_seconds: settle,
      reset_baseline: !!extra?.reset_baseline,
    }, extra || {});
    return api('/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
  }

  function updateToggleButton(status) {
    const btn = document.getElementById('obs-watch-toggle');
    if (!btn) return;
    watching = !!(status && status.enabled && status.running);
    btn.textContent = watching ? 'Stop watching' : 'Start watching';
    btn.classList.toggle('btn-danger', watching);
    btn.classList.toggle('btn-primary', !watching);
  }

  function describeStatus(status) {
    if (!status) return 'Not watching.';
    if (!status.folder) return 'Choose the OBS recording folder (mounted SMB share).';
    if (!status.folder_ok) return 'Folder not reachable — remount the network share, then Start watching.';
    if (status.enabled && status.running) {
      return `Watching · settle ${status.settle_seconds}s · recording ${status.recording_count} · ready ${status.ready_count}`;
    }
    if (status.enabled) return 'Enabled, starting watcher…';
    return `Folder saved. Press Start watching when OBS is recording.`;
  }

  function renderList(recordings) {
    const root = document.getElementById('obs-watch-list');
    if (!root) return;
    root.replaceChildren();
    const active = (recordings || []).filter(r => r.status === 'recording' || r.status === 'ready');
    const recent = (recordings || []).filter(r => r.status === 'imported' || r.status === 'dismissed').slice(0, 5);
    const show = active.concat(recent);
    if (!show.length) {
      const empty = document.createElement('p');
      empty.className = 'muted small';
      empty.textContent = 'No recordings detected yet. Start OBS recording into this folder.';
      root.append(empty);
      return;
    }
    for (const rec of show) {
      const row = document.createElement('div');
      row.className = 'obs-watch-item status-' + rec.status;
      const title = document.createElement('div');
      title.className = 'obs-watch-item-title';
      const badge = rec.status === 'recording' ? '● Recording'
        : rec.status === 'ready' ? '✓ Ready'
        : rec.status === 'imported' ? 'Added'
        : 'Dismissed';
      title.textContent = `${badge} · ${rec.name} · ${fmtBytes(rec.size)}${rec.status === 'recording' ? fmtRate(rec.bytes_per_sec) : ''}`;
      row.append(title);
      const path = document.createElement('p');
      path.className = 'muted small obs-watch-path';
      path.textContent = rec.path;
      row.append(path);
      const actions = document.createElement('div');
      actions.className = 'obs-watch-item-actions';
      if (rec.status === 'ready' || rec.status === 'recording') {
        const useBtn = document.createElement('button');
        useBtn.className = 'btn btn-small btn-primary';
        useBtn.textContent = rec.status === 'ready' ? 'Use in project' : 'Use anyway';
        useBtn.title = rec.status === 'recording'
          ? 'File may still be growing — prefer waiting until Ready'
          : 'Add this recording as the current video';
        useBtn.onclick = () => useRecording(rec, useBtn);
        actions.append(useBtn);
        const dismissBtn = document.createElement('button');
        dismissBtn.className = 'btn btn-small btn-secondary';
        dismissBtn.textContent = 'Dismiss';
        dismissBtn.onclick = async () => {
          try {
            await api(`/recordings/${encodeURIComponent(rec.id)}/dismiss`, { method: 'POST' });
            await refresh();
          } catch (err) { setStatus(err.message); }
        };
        actions.append(dismissBtn);
      }
      row.append(actions);
      root.append(row);
    }
  }

  async function useRecording(rec, btn) {
    if (btn) btn.disabled = true;
    try {
      if (typeof addSourceFiles === 'function') {
        sourceSelectionMode = 'add';
        addSourceFiles([{ path: rec.path, name: 'OBS · ' + rec.name }]);
      }
      try {
        await api(`/recordings/${encodeURIComponent(rec.id)}/imported`, { method: 'POST' });
      } catch (_) { /* non-fatal */ }
      setStatus('Added to project: ' + rec.name);
      if (typeof showToast === 'function') showToast('OBS recording added', 'success');
      await refresh();
    } catch (err) {
      setStatus(err.message);
      if (btn) btn.disabled = false;
    }
  }

  async function refresh() {
    if (pollBusy) return;
    pollBusy = true;
    try {
      const data = await api('/recordings');
      updateToggleButton(data.status);
      const folderInput = document.getElementById('obs-watch-folder');
      const settleInput = document.getElementById('obs-watch-settle');
      if (folderInput && data.status?.folder && document.activeElement !== folderInput) {
        folderInput.value = data.status.folder;
      }
      if (settleInput && data.status?.settle_seconds && document.activeElement !== settleInput) {
        settleInput.value = data.status.settle_seconds;
      }
      setStatus(describeStatus(data.status));
      renderList(data.recordings || []);
      schedulePoll(data.status?.enabled);
    } catch (err) {
      setStatus(err.message);
      schedulePoll(watching);
    } finally {
      pollBusy = false;
    }
  }

  function schedulePoll(active) {
    clearTimeout(pollTimer);
    pollTimer = setTimeout(refresh, active ? 4000 : 15000);
  }

  async function toggleWatch() {
    const btn = document.getElementById('obs-watch-toggle');
    if (btn) btn.disabled = true;
    try {
      await saveConfig({ reset_baseline: !watching });
      if (watching) {
        await api('/stop', { method: 'POST' });
      } else {
        await api('/start', { method: 'POST' });
        if (typeof showToast === 'function') showToast('Watching OBS folder', 'success');
      }
      await refresh();
    } catch (err) {
      setStatus(err.message);
      if (typeof showAlert === 'function') showAlert(err.message);
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  async function browseFolder() {
    try {
      if (!window.clipperAPI?.selectOutputFolder) {
        setStatus('Open the desktop app to browse for a folder.');
        return;
      }
      const current = (document.getElementById('obs-watch-folder')?.value || '').trim();
      const path = await window.clipperAPI.selectOutputFolder(current || undefined);
      if (!path) return;
      document.getElementById('obs-watch-folder').value = path;
      await saveConfig({ folder: path, reset_baseline: true });
      await refresh();
    } catch (err) {
      setStatus(err.message);
    }
  }

  function wire() {
    document.getElementById('obs-watch-browse')?.addEventListener('click', browseFolder);
    document.getElementById('obs-watch-toggle')?.addEventListener('click', toggleWatch);
    document.getElementById('obs-watch-save')?.addEventListener('click', async () => {
      try {
        await saveConfig({ reset_baseline: true });
        setStatus('Folder saved.');
        await refresh();
      } catch (err) { setStatus(err.message); }
    });
    document.getElementById('obs-watch-scan')?.addEventListener('click', async () => {
      try {
        await saveConfig({});
        await api('/scan', { method: 'POST' });
        await refresh();
      } catch (err) { setStatus(err.message); }
    });
    document.getElementById('obs-watch-panel')?.addEventListener('toggle', (e) => {
      if (e.target.open) refresh();
    });
    // Soft-load status after app boot.
    setTimeout(refresh, 2500);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', wire);
  } else {
    wire();
  }
})();
