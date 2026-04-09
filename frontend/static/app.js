/* VideoDL — Main Application JS */
/* Generated from index.html */

'use strict';


const API = '/api/v1';
let authToken    = localStorage.getItem('vdl_token') || null;
let isBulkMode   = false;
let isProcessing = false;

function getHistoryKey() {

  if (!authToken) return null;
  const user = localStorage.getItem('vdl_user');
  if (user) {
    try {
      const u = JSON.parse(user);
      return 'vdl_history_' + (u.username || u.email || 'guest').replace(/[^a-z0-9]/gi,'_');
    } catch(e) {}
  }
  return 'vdl_history_user';
}
let history = authToken ? JSON.parse(localStorage.getItem(getHistoryKey()) || '[]') : [];

const urlInput     = document.getElementById('urlInput');
const clearBtn     = document.getElementById('clearBtn');
const analyzeBtn   = document.getElementById('analyzeBtn');
const toggleBulk   = document.getElementById('toggleBulk');
const bulkWrap     = document.getElementById('bulkWrap');
const bulkInput    = document.getElementById('bulkInput');
const detectBar    = document.getElementById('detectBar');
const detectPlatform = document.getElementById('detectPlatform');
const detectNote   = document.getElementById('detectNote');
const progressWrap = document.getElementById('progressWrap');
const progressLabel= document.getElementById('progressLabel');
const progressPct  = document.getElementById('progressPct');
const progressFill = document.getElementById('progressFill');
const progressSub  = document.getElementById('progressSub');
const statusMsg    = document.getElementById('statusMsg');
const resultCard   = document.getElementById('resultCard');
const resultPreview= document.getElementById('resultPreview');
const resultTitle  = document.getElementById('resultTitle');
const resultMeta   = document.getElementById('resultMeta');
const resultActions= document.getElementById('resultActions');
const optionsList  = document.getElementById('optionsList');
const historySection=document.getElementById('historySection');
const historyList  = document.getElementById('historyList');

const PLATFORM_MAP = [
  { re:/youtube\.com|youtu\.be/, name:'YouTube', icon:'▶️', note:'Video / Short' },
  { re:/instagram\.com|instagr\.am|instagram\.com\/stories/, name:'Instagram', icon:'📸', note:'Post / Reel / Story' },

  { re:/twitter\.com|x\.com/, name:'Twitter / X', icon:'🐦', note:'Tweet Media' },
  { re:/facebook\.com|fb\.com|fb\.watch/, name:'Facebook', icon:'📘', note:'Video / Photo' },
  { re:/reddit\.com|redd\.it/, name:'Reddit', icon:'🤖', note:'Video / Image / GIF' },

  { re:/\.(jpg|jpeg|png|gif|webp|svg|avif|bmp)(\?|$)/i, name:'Direct Image', icon:'🖼️', note:'Image File' },
  { re:/\.(mp4|mov|webm|avi|mkv|m4v)(\?|$)/i, name:'Direct Video', icon:'🎬', note:'Video File' },
  { re:/\.(mp3|wav|ogg|flac|aac|m4a)(\?|$)/i, name:'Direct Audio', icon:'🎵', note:'Audio File' },
  { re:/\.(pdf)(\?|$)/i, name:'PDF Document', icon:'📄', note:'Document' },
];

function detectClientSide(url) {
  for (const p of PLATFORM_MAP) {
    if (p.re.test(url)) return p;
  }
  return null;
}

function resetUI(keepDetect = false) {
  hideBulkDoneOverlay();
  progressWrap.classList.remove('show');
  statusMsg.classList.remove('show','success','error','info');
  resultCard.classList.remove('show');
  if (!keepDetect) detectBar.classList.remove('show');
  setProgress(0,'','');
}

function setProgress(pct, label, sub) {
  progressFill.style.width = pct + '%';
  progressPct.textContent  = pct + '%';
  progressLabel.textContent = label;
  progressSub.textContent   = sub;
}

function animateProgress(from, to, ms, label, sub) {
  return new Promise(resolve => {
    const start = performance.now();
    progressWrap.classList.add('show');
    function step(now) {
      const t   = Math.min((now - start) / ms, 1);
      const ease= t < 0.5 ? 2*t*t : -1+(4-2*t)*t;
      setProgress(Math.round(from + (to-from)*ease), label, sub);
      t < 1 ? requestAnimationFrame(step) : resolve();
    }
    requestAnimationFrame(step);
  });
}

function showStatus(type, html) {
  statusMsg.className = `status-msg show ${type}`;
  statusMsg.innerHTML = html;
}

function formatBytes(b) {
  if (!b) return '';
  if (b < 1024) return b + ' B';
  if (b < 1048576) return (b/1024).toFixed(1) + ' KB';
  return (b/1048576).toFixed(1) + ' MB';
}

function setBtnLoading(loading) {
  isProcessing = loading;
  analyzeBtn.disabled = loading;
  analyzeBtn.innerHTML = loading
    ? `<div class="spinner"></div> Analyzing...`
    : `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg> Fetch`;
}

let detectTimeout;
urlInput.addEventListener('input', () => {
  const val = urlInput.value.trim();
  clearBtn.classList.toggle('show', val.length > 0);
  resetUI(false);
  clearTimeout(detectTimeout);
  if (!val) { detectBar.classList.remove('show'); return; }
  detectTimeout = setTimeout(() => {
    const p = detectClientSide(val);
    if (p) {
      detectPlatform.textContent = `${p.icon} ${p.name}`;
      detectNote.textContent     = p.note;
      detectBar.classList.add('show');
    } else {
      detectBar.classList.remove('show');
    }
  }, 350);
});

clearBtn.addEventListener('click', () => {
  urlInput.value = '';
  clearBtn.classList.remove('show');
  detectBar.classList.remove('show');
  resetUI(false);
});

urlInput.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); triggerAnalyze(); }
});

toggleBulk.addEventListener('click', () => {
  isBulkMode = !isBulkMode;
  bulkWrap.classList.toggle('show', isBulkMode);
  urlInput.style.display = isBulkMode ? 'none' : '';
  document.querySelector('.url-icon').style.display = isBulkMode ? 'none' : '';

  // Update button appearance
  const bulkIcon = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/></svg>`;
  const closeIcon = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>`;
  if (isBulkMode) {
    toggleBulk.innerHTML = closeIcon + ' Single';
    toggleBulk.classList.add('active');
    toggleBulk.title = 'Switch to Single Mode';
  } else {
    toggleBulk.innerHTML = bulkIcon + ' Bulk';
    toggleBulk.classList.remove('active');
    toggleBulk.title = 'Switch to Bulk Mode';
  }

  // Clear everything when switching modes
  hideBulkDoneOverlay();
  bulkInput.value = '';
  urlInput.value = '';
  clearBtn.classList.remove('show');
  detectBar.classList.remove('show');
  resultCard.classList.remove('show');
  progressWrap.classList.remove('show');
  statusMsg.className = 'status-msg';
  statusMsg.innerHTML = '';
  optionsList.innerHTML = '';
  resultActions.innerHTML = '';
  resultPreview.innerHTML = '';
  resultTitle.textContent = '';
  resultMeta.innerHTML = '';
  window._lastResultData = null;
  window._lastSourceUrl  = null;

  if (isBulkMode) {
    bulkInput.focus();
    showStatus('info', '📦 Bulk mode — paste up to 20 URLs, one per line.');
  } else {
    setTimeout(() => urlInput.focus(), 50);
  }
});

analyzeBtn.addEventListener('click', triggerAnalyze);

document.addEventListener('keydown', e => {
  if (e.key === 'v' && (e.ctrlKey || e.metaKey) && document.activeElement !== urlInput) {
    urlInput.focus();
  }
});

async function triggerAnalyze() {
  if (isProcessing) return;

  if (isBulkMode) {
    await triggerBulk();
    return;
  }

  const url = urlInput.value.trim();
  if (!url) { urlInput.focus(); showStatus('error', '⚠️ Please paste a URL first.'); return; }

  resetUI(true);
  setBtnLoading(true);

  try {
    await animateProgress(0, 30, 500, 'Connecting...', url.slice(0, 60));
    await animateProgress(30, 65, 700, 'Extracting media info...', 'Analyzing source');

    const quality = 'best';
    const res = await fetch(`${API}/download/analyze`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}) },
      body: JSON.stringify({ url, quality }),
    });

    const data = await res.json();
    await animateProgress(65, 100, 400, 'Done!', '');

    if (!data.success) {
      showStatus('error', `❌ ${data.error || 'Could not process this URL.'}`);
      return;
    }

    renderResult(data, url);
    addToHistory(url, data.platform, data.title);
  } catch (e) {
    showStatus('error', `❌ ${e.message || 'Network error. Is the server running?'}`);
  } finally {
    setBtnLoading(false);
  }
}

async function triggerBulk() {
  const raw  = bulkInput.value.trim();
  const urls = [...new Set(raw.split('\n').map(u => u.trim()).filter(u => u.length > 5 && u.includes('.')))];
  if (!urls.length) { showStatus('error','⚠️ Enter at least one URL.'); return; }
  if (urls.length > 20) { showStatus('error','⚠️ Maximum 20 URLs per bulk request.'); return; }

  resetUI(true);
  setBtnLoading(true);

  try {
    await animateProgress(0, 20, 400, `Preparing ${urls.length} URLs...`, 'This may take a moment');
    const res  = await fetch(`${API}/download/bulk`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}) },
      body: JSON.stringify({ urls, quality: 'best' }),
    });
    const data = await res.json();
    await animateProgress(40, 100, 500, 'Done!', '');

    renderBulkResults(data);
    if (data.success_count === data.total) {
      showStatus('success', `✅ All ${data.total} URLs processed successfully!`);
    } else if (data.success_count === 0) {
      showStatus('error', `❌ All URLs failed. Check if posts are public.`);
    } else {
      showStatus('info', `⚠️ ${data.success_count}/${data.total} URLs succeeded. ${data.total - data.success_count} failed — may be private posts.`);
    }
  } catch (e) {
    showStatus('error', `❌ ${e.message}`);
  } finally {
    setBtnLoading(false);
  }
}

function renderResult(data, sourceUrl) {
  // Reset result card to fully clean state before rendering
  resultCard.classList.remove('show');
  resultCard.style.position = '';
  optionsList.innerHTML   = '';
  resultActions.innerHTML = '';
  resultPreview.innerHTML = '';
  resultTitle.textContent = '';
  resultMeta.innerHTML    = '';
  hideBulkDoneOverlay(); // safety — remove any lingering overlay
  resultTitle.textContent = data.title || sourceUrl;

  const tags = [];
  if (data.platform) tags.push(`<span class="meta-tag">${data.platform}</span>`);
  if (data.media_type) tags.push(`<span class="meta-tag">${data.media_type}</span>`);
  resultMeta.innerHTML = tags.join('');

  resultPreview.innerHTML = '';
  if (data.thumbnail) {
    const img = document.createElement('img');
    img.className = 'result-preview';
    img.src = data.thumbnail;
    img.alt = data.title || 'Preview';
    img.onerror = () => img.remove();
    resultPreview.appendChild(img);
  }

  resultActions.innerHTML = '';
  if (data.options.length === 1) {
    const opt = data.options[0];
    const btn = document.createElement('button');
    btn.className = 'action-btn primary';
    const dlIcon = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>`;
    btn.innerHTML = `${dlIcon} Download ${opt.format?.toUpperCase() || opt.media_type}`;
    btn.onclick = async function() {
      if (btn.disabled) return;
      btn.disabled = true;
      btn.innerHTML = `<span class="spinner"></span> Downloading...`;
      try {
        await streamDownload(opt.url, opt.label, false); // single mode
      } finally {
        setTimeout(() => {
          btn.disabled = false;
          btn.innerHTML = `${dlIcon} Download ${opt.format?.toUpperCase() || opt.media_type}`;
        }, 3000);
      }
    };
    resultActions.appendChild(btn);
  }

  const openBtn = document.createElement('button');
  openBtn.className = 'action-btn';
  openBtn.innerHTML = '🔗 Open Source';
  openBtn.onclick = () => window.open(sourceUrl, '_blank');
  resultActions.appendChild(openBtn);

  optionsList.innerHTML = '';
  if (data.options.length > 1) {

    // Get selected quality from dropdown
    const selectedQuality = 'best'; // best, 1080p, 720p, 480p, 360p, audio

    // Filter options based on selected quality
    let filteredOptions = data.options;

    if (selectedQuality === 'audio') {
      // Audio Only — show only MP3/audio options
      const audioOpts = data.options.filter(o =>
        (o.format || '').toLowerCase().includes('mp3') ||
        (o.label  || '').toLowerCase().includes('mp3') ||
        (o.label  || '').toLowerCase().includes('audio') ||
        (o.label  || '').toLowerCase().includes('kbps')
      );
      filteredOptions = audioOpts.length > 0 ? audioOpts : data.options;
    } else if (selectedQuality !== 'best') {
      // Specific quality selected (720p, 1080p etc) — filter to matching
      const qOpts = data.options.filter(o =>
        (o.label || '').toLowerCase().includes(selectedQuality.replace('p',''))
      );
      filteredOptions = qOpts.length > 0 ? qOpts : data.options;
    }

    // Sort: best quality first (largest file size), audio last
    filteredOptions.sort((a, b) => {
      const aIsAudio = (a.label||'').toLowerCase().includes('mp3') || (a.label||'').toLowerCase().includes('kbps');
      const bIsAudio = (b.label||'').toLowerCase().includes('mp3') || (b.label||'').toLowerCase().includes('kbps');
      if (aIsAudio && !bIsAudio) return 1;
      if (!aIsAudio && bIsAudio) return -1;
      return (b.file_size || 0) - (a.file_size || 0);
    });

    filteredOptions.forEach((opt, idx) => {
      const isAudio = (opt.label||'').toLowerCase().includes('mp3') || (opt.label||'').toLowerCase().includes('kbps');
      const isBest  = idx === 0 && !isAudio;
      const item = document.createElement('div');
      item.className = 'option-item' + (isBest ? ' option-item-best' : '');
      item.innerHTML = `
        <div class="option-left">
          <div class="option-label">${opt.label}${isBest ? ' <span class="best-badge">BEST</span>' : ''}</div>
          <div class="option-meta">${opt.format ? opt.format.toUpperCase() : ''}${opt.file_size ? ' · ' + formatBytes(opt.file_size) : ''}${opt.width ? ' · ' + opt.width + '×' + opt.height : ''}</div>
        </div>
        <button class="option-dl-btn" data-url="${opt.url}" data-label="${opt.label}">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
          Download
        </button>`;

      const dlBtn = item.querySelector('.option-dl-btn');
      dlBtn.onclick = async function() {
        // Prevent multiple clicks
        if (dlBtn.disabled) return;
        dlBtn.disabled = true;
        dlBtn.innerHTML = `<span class="btn-spinner"></span> Downloading...`;
        dlBtn.style.opacity = '0.7';
        try {
          await streamDownload(opt.url, opt.label, false); // single mode
        } finally {
          setTimeout(() => {
            dlBtn.disabled = false;
            dlBtn.innerHTML = `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg> Download`;
            dlBtn.style.opacity = '1';
          }, 3000);
        }
      };
      optionsList.appendChild(item);
    });
  }

  window._lastResultData = data;
  window._lastSourceUrl  = sourceUrl;
  resultCard.classList.add('show');
  showStatus('success', `✅ Found ${data.options.length} download option${data.options.length !== 1 ? 's' : ''} for <strong>${data.platform || 'this URL'}</strong>.`);
  resultCard.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function renderBulkResults(data) {
  resultPreview.innerHTML = '';
  resultTitle.textContent = `Bulk Results — ${data.success_count}/${data.total} succeeded`;
  resultMeta.innerHTML = `<span class="meta-tag">Bulk</span><span class="meta-tag">${data.total} URLs</span>`;
  resultActions.innerHTML = '';
  optionsList.innerHTML = '';

  data.results.forEach((r, i) => {
    const item = document.createElement('div');
    item.className = 'option-item';

    if (!r.success) {
      // Failed URL
      item.innerHTML = `
        <div class="option-left">
          <div class="option-label" style="color:var(--red)">❌ ${(r.url||'').slice(0,55)}</div>
          <div class="option-meta">${r.error || 'Failed to fetch'}</div>
        </div>`;
    } else {
      // Success — pick best option based on quality dropdown
      const selectedQuality = 'best';
      let bestOpt = r.options[0];

      if (selectedQuality === 'audio') {
        const audioOpt = r.options.find(o =>
          (o.label||'').toLowerCase().includes('mp3') ||
          (o.label||'').toLowerCase().includes('kbps')
        );
        if (audioOpt) bestOpt = audioOpt;
      } else if (selectedQuality !== 'best') {
        const qOpt = r.options.find(o =>
          (o.label||'').toLowerCase().includes(selectedQuality.replace('p',''))
        );
        if (qOpt) bestOpt = qOpt;
      } else {
        // Best = largest file size video
        const videoOpts = r.options.filter(o =>
          !(o.label||'').toLowerCase().includes('mp3') &&
          !(o.label||'').toLowerCase().includes('kbps')
        );
        if (videoOpts.length) {
          bestOpt = videoOpts.reduce((a,b) => (b.file_size||0) > (a.file_size||0) ? b : a);
        }
      }

      const shortUrl = (r.url||'').replace(/^https?:\/\/(www\.)?/,'').slice(0,45);
      item.innerHTML = `
        <div class="option-left">
          <div class="option-label">✅ ${r.title || shortUrl}</div>
          <div class="option-meta">${r.platform||''} · ${bestOpt ? bestOpt.label : ''} · ${r.options.length} option${r.options.length!==1?'s':''}</div>
        </div>
        ${bestOpt ? `<button class="option-dl-btn bulk-dl-btn">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
          Download
        </button>` : ''}`;

      if (bestOpt) {
        const dlBtn = item.querySelector('.bulk-dl-btn');
        dlBtn.onclick = async function() {
          if (dlBtn.disabled) return;
          dlBtn.disabled = true;
          dlBtn.innerHTML = `<span class="btn-spinner"></span> Downloading...`;
          dlBtn.style.opacity = '0.7';
          try {
            await streamDownload(bestOpt.url, bestOpt.label, true); // bulk=true → no reset
          } finally {
            setTimeout(() => {
              dlBtn.disabled = false;
              dlBtn.innerHTML = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg> Download`;
              dlBtn.style.opacity = '1';
            }, 3000);
          }
        };
      }
    }
    optionsList.appendChild(item);
  });

  // Add "Download All" button for bulk mode
  if (data.results && data.results.length > 1) {
    const successResults = data.results.filter(r => r.success && r.options && r.options.length > 0);
    if (successResults.length > 1) {
      const dlAllWrap = document.createElement('div');
      dlAllWrap.style.cssText = 'padding:14px 0 4px;';
      const dlAllBtn = document.createElement('button');
      dlAllBtn.className = 'dl-btn';
      dlAllBtn.style.cssText = 'width:100%;justify-content:center;margin-bottom:8px;';
      dlAllBtn.innerHTML = `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg> Download All (${successResults.length} videos)`;

      let isDownloadingAll = false;
      dlAllBtn.onclick = async function() {
        if (isDownloadingAll) return;
        isDownloadingAll = true;
        dlAllBtn.disabled = true;

        // Download one by one with 1s gap
        for (let i = 0; i < successResults.length; i++) {
          const r = successResults[i];
          const selectedQuality = 'best';
          let bestOpt = r.options[0];
          if (selectedQuality === 'audio') {
            const a = r.options.find(o => (o.label||'').toLowerCase().includes('mp3') || (o.label||'').toLowerCase().includes('kbps'));
            if (a) bestOpt = a;
          } else if (selectedQuality !== 'best') {
            const q = r.options.find(o => (o.label||'').toLowerCase().includes(selectedQuality.replace('p','')));
            if (q) bestOpt = q;
          }
          if (bestOpt) {
            dlAllBtn.innerHTML = `<span class="btn-spinner"></span> Downloading ${i+1}/${successResults.length}...`;
            await streamDownload(bestOpt.url, bestOpt.label, true);
            if (i < successResults.length - 1) await new Promise(r => setTimeout(r, 1200));
          }
        }

        dlAllBtn.innerHTML = `✅ All ${successResults.length} downloads started!`;
        dlAllBtn.style.background = 'var(--green)';

        // Show professional Done state after 2 seconds
        setTimeout(() => showBulkDoneState(successResults.length), 2000);
      };
      dlAllWrap.appendChild(dlAllBtn);
      optionsList.insertBefore(dlAllWrap, optionsList.firstChild);
    }
  }

  resultCard.classList.add('show');
}

function showBulkDoneState(count) {
  // Hide the result card completely — no overlay, no DOM tricks
  resultCard.classList.remove('show');

  // Clear all result card content so next single fetch starts fresh
  optionsList.innerHTML   = '';
  resultActions.innerHTML = '';
  resultPreview.innerHTML = '';
  resultTitle.textContent = '';
  resultMeta.innerHTML    = '';
  resultCard.style.position = '';
  window._lastResultData  = null;
  window._lastSourceUrl   = null;

  // Show done state in the status bar — simple, clean, no DOM conflicts
  statusMsg.className = 'status-msg show success';
  statusMsg.innerHTML = `
    <div style="width:100%">
      <div style="font-size:22px;margin-bottom:6px;">🎉 All ${count} video${count !== 1 ? 's' : ''} downloaded!</div>
      <div style="font-size:12px;color:var(--text-2);margin-bottom:16px;">Your files are in your Downloads folder. Ready for more?</div>
      <div style="display:flex;gap:10px;flex-wrap:wrap;">
        <button onclick="startNewBulk()" style="padding:10px 20px;border-radius:10px;background:var(--amber);border:none;color:#0c0c0f;font-size:13px;font-weight:700;cursor:pointer;font-family:'Cabinet Grotesk',sans-serif;">
          📦 New Bulk Download
        </button>
        <button onclick="switchToSingleMode()" style="padding:10px 20px;border-radius:10px;background:var(--surface);border:1px solid var(--border);color:var(--text);font-size:13px;font-weight:700;cursor:pointer;font-family:'Cabinet Grotesk',sans-serif;">
          ↓ Single Download
        </button>
      </div>
    </div>`;
}

function hideBulkDoneOverlay() {
  // No-op — kept for backwards compatibility with any existing calls
  // Done state is now in statusMsg, not an overlay
  resultCard.style.position = '';
}

function startNewBulk() {
  hideBulkDoneOverlay();
  bulkInput.value = '';
  resultCard.classList.remove('show');
  optionsList.innerHTML = '';
  resultActions.innerHTML = '';
  resultPreview.innerHTML = '';
  resultTitle.textContent = '';
  progressWrap.classList.remove('show');
  statusMsg.className = 'status-msg';
  window._lastResultData = null;
  window.scrollTo({ top: 0, behavior: 'smooth' });
  setTimeout(() => bulkInput.focus(), 100);
}

function switchToSingleMode() {
  hideBulkDoneOverlay();
  if (isBulkMode) {
    isBulkMode = false;
    bulkWrap.classList.remove('show');
    const bulkIcon = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/></svg>`;
    toggleBulk.innerHTML = bulkIcon + ' Bulk';
    toggleBulk.classList.remove('active');
    toggleBulk.title = 'Switch to Bulk Mode';
    urlInput.style.display = '';
    document.querySelector('.url-icon').style.display = '';
    bulkInput.value = '';
  }
  // Clear result card completely
  resultCard.classList.remove('show');
  resultCard.style.position = '';
  optionsList.innerHTML   = '';
  resultActions.innerHTML = '';
  resultPreview.innerHTML = '';
  resultTitle.textContent = '';
  resultMeta.innerHTML    = '';
  // Clear all status / progress
  progressWrap.classList.remove('show');
  statusMsg.className = 'status-msg'; // hides done state
  statusMsg.innerHTML = '';
  urlInput.value = '';
  clearBtn.classList.remove('show');
  detectBar.classList.remove('show');
  window._lastResultData = null;
  window._lastSourceUrl  = null;
  window.scrollTo({ top: 0, behavior: 'smooth' });
  setTimeout(() => urlInput.focus(), 100);
}

async function streamDownload(url, label, isBulk = false) {
  try {
    const res = await fetch(`${API}/download/fetch`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}) },
      body: JSON.stringify({ url, filename: label }),
    });
    if (!res.ok) throw new Error(await res.text());
    const blob = await res.blob();
    const a    = document.createElement('a');
    a.href     = URL.createObjectURL(blob);
    a.download = label.replace(/[^\w\s.-]/g, '_');
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    showStatus('success', `✅ Download started: <strong>${label}</strong>`);

    // Only show "Download Another" prompt in SINGLE mode
    // In BULK mode: user can download all videos without reset
    if (!isBulk && !isBulkMode) {
      setTimeout(() => showDownloadAnotherPrompt(), 1500);
    }

  } catch {
    window.open(url, '_blank');
    if (!isBulk && !isBulkMode) {
      setTimeout(() => showDownloadAnotherPrompt(), 2000);
    }
  }
}

function showDownloadAnotherPrompt() {
  // Clear URL input
  const urlInput = document.getElementById('urlInput');
  if (urlInput) {
    urlInput.value = '';
    urlInput.dispatchEvent(new Event('input'));
  }
  // Clear detect bar
  const detectBar = document.getElementById('detectBar');
  if (detectBar) detectBar.classList.remove('show');

  // Show a clean "ready for next" state on result card
  const resultCard = document.getElementById('resultCard');
  if (resultCard && resultCard.classList.contains('show')) {
    const body = resultCard.querySelector('.result-body');
    if (body) {
      body.innerHTML = `
        <div style="text-align:center;padding:20px 0;">
          <div style="font-size:40px;margin-bottom:12px;">✅</div>
          <div style="font-size:16px;font-weight:700;color:var(--green);margin-bottom:8px;">Download started!</div>
          <div style="font-size:13px;color:var(--text-2);margin-bottom:20px;">Your file is being downloaded. Paste another URL to download more.</div>
          <button onclick="resetForNextDownload()" style="padding:10px 24px;border-radius:10px;background:var(--amber);border:none;color:#0c0c0f;font-size:14px;font-weight:700;cursor:pointer;font-family:'Cabinet Grotesk',sans-serif;">
            ↓ Download Another
          </button>
        </div>`;
    }
  }
}

function resetForNextDownload() {
  // Full reset — clear everything
  const urlInput = document.getElementById('urlInput');
  if (urlInput) { urlInput.value = ''; urlInput.focus(); }
  const clearBtn = document.getElementById('clearBtn');
  if (clearBtn) clearBtn.classList.remove('show');
  const detectBar = document.getElementById('detectBar');
  if (detectBar) detectBar.classList.remove('show');
  const progressWrap = document.getElementById('progressWrap');
  if (progressWrap) progressWrap.classList.remove('show');
  const statusMsg = document.getElementById('statusMsg');
  if (statusMsg) statusMsg.className = 'status-msg';
  const resultCard = document.getElementById('resultCard');
  if (resultCard) resultCard.classList.remove('show');
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

function addToHistory(url, platform, title, media_type, file_size) {
  const entry = {
    url,
    platform: platform || 'unknown',
    title: title || url,
    media_type: media_type || 'video',
    file_size: file_size || 0,
    time: Date.now()
  };
  history.unshift(entry);
  if (history.length > 100) history.pop();

  const key = getHistoryKey();
  if (key) localStorage.setItem(key, JSON.stringify(history));
  renderHistory();
}

function renderHistory() {
  if (!authToken || !history.length) { historySection.style.display = 'none'; return; }
  historySection.style.display = 'block';
  historyList.innerHTML = '';
  const ICONS = { youtube:'▶️', instagram:'📸', twitter:'🐦', facebook:'📘', reddit:'🤖', direct:'🖼️', image:'🖼️', video:'🎬', audio:'🎵', document:'📄', unknown:'🔗' };
  history.slice(0,6).forEach(h => {
    const ago   = timeAgo(h.time);
    const icon  = ICONS[h.platform?.toLowerCase()] || '🔗';
    const item  = document.createElement('div');
    item.className = 'history-item';
    item.innerHTML = `
      <div class="history-icon">${icon}</div>
      <div class="history-info">
        <div class="history-url">${h.url}</div>
        <div class="history-platform">${h.platform || 'Unknown'}</div>
      </div>
      <div class="history-time">${ago}</div>
      <button class="history-use" title="Re-fetch">↩</button>`;
    item.querySelector('.history-use').addEventListener('click', e => {
      e.stopPropagation();
      urlInput.value = h.url;
      urlInput.dispatchEvent(new Event('input'));
      window.scrollTo({ top: 0, behavior: 'smooth' });
    });
    item.addEventListener('click', () => {
      urlInput.value = h.url;
      urlInput.dispatchEvent(new Event('input'));
      window.scrollTo({ top: 0, behavior: 'smooth' });
    });
    historyList.appendChild(item);
  });
}

function timeAgo(ts) {
  const s = Math.floor((Date.now() - ts) / 1000);
  if (s < 60)   return s + 's';
  if (s < 3600)  return Math.floor(s/60) + 'm';
  if (s < 86400) return Math.floor(s/3600) + 'h';
  return Math.floor(s/86400) + 'd';
}

const themeToggle = document.getElementById('themeToggle');
let isDark = localStorage.getItem('vdl_theme') !== 'light';

function applyTheme() {
  document.documentElement.setAttribute('data-theme', isDark ? 'dark' : 'light');
  themeToggle.textContent = isDark ? '🌙' : '☀️';
  localStorage.setItem('vdl_theme', isDark ? 'dark' : 'light');
}
applyTheme();
themeToggle.addEventListener('click', () => { isDark = !isDark; applyTheme(); });

const authModal    = document.getElementById('authModal');
const loginForm    = document.getElementById('loginForm');
const registerForm = document.getElementById('registerForm');

document.getElementById('openLogin').addEventListener('click', () => {
  loginForm.style.display = ''; registerForm.style.display = 'none';
  authModal.classList.add('show');

  document.getElementById('loginEmail').value = '';
  document.getElementById('loginPassword').value = '';
});
document.getElementById('openRegister').addEventListener('click', () => {
  const alreadyShowingRegister = authModal.classList.contains('show') && registerForm.style.display !== 'none';
  loginForm.style.display = 'none'; registerForm.style.display = '';
  authModal.classList.add('show');

  // Only clear fields on first open, not when user clicks Sign Up again mid-fill
  if (!alreadyShowingRegister) {
    document.getElementById('regEmail').value = '';
    document.getElementById('regUsername').value = '';
    document.getElementById('regPassword').value = '';
    const hint = document.getElementById('passwordHint');
    if (hint) hint.innerHTML = '';
    const uHint = document.getElementById('usernameHint');
    if (uHint) { uHint.style.color = 'var(--text-3)'; uHint.textContent = "Only letters, numbers, dots (.), hyphens (-), underscores (_). No spaces."; }
  }
});
document.getElementById('closeModal').addEventListener('click', () => {
  authModal.classList.remove('show');
  setTimeout(() => {
    showLoginForm(); // This handles all clearing
    document.getElementById('loginEmail').value = '';
    document.getElementById('loginPassword').value = '';
  }, 300);
});
authModal.addEventListener('click', e => {
  if (e.target === authModal) {
    authModal.classList.remove('show');
    setTimeout(() => {
      showLoginForm();
      document.getElementById('loginEmail').value = '';
      document.getElementById('loginPassword').value = '';
    }, 300);
  }
});
document.getElementById('switchToRegister').addEventListener('click', () => {
  _hideAllForms();
  document.getElementById('registerForm').style.display = '';
  document.getElementById('regEmail').value = '';
  document.getElementById('regUsername').value = '';
  document.getElementById('regPassword').value = '';
});
document.getElementById('switchToLogin').addEventListener('click', () => {
  _hideAllForms();
  document.getElementById('loginForm').style.display = '';
});

function toggleUserMenu() {
  document.getElementById('userMenu').classList.toggle('open');
}
function closeUserMenu() {
  document.getElementById('userMenu').classList.remove('open');
}
document.addEventListener('click', e => {

  const menu = document.getElementById('userMenu');
  if (menu && !menu.contains(e.target)) closeUserMenu();
});

window.addEventListener('load', function() {
  const overlay = document.getElementById('dlPanelOverlay');
  if (overlay) {
    overlay.addEventListener('click', function(e) {
      if (e.target === this) closeDlPanelBtn();
    });
  }
});

function handleLogout() {
  authToken = null;
  localStorage.removeItem('vdl_token');
  localStorage.removeItem('vdl_user');

  document.getElementById('authButtons').style.display = '';
  document.getElementById('userMenu').style.display = 'none';
  closeUserMenu();

  const rc = document.getElementById('resultCard');
  if (rc) rc.classList.remove('show');

  if (urlInput) { urlInput.value = ''; urlInput.dispatchEvent(new Event('input')); }

  const sm = document.getElementById('statusMsg');
  if (sm) { sm.style.display = 'none'; sm.textContent = ''; }

  const pw = document.getElementById('progressWrap');
  if (pw) pw.style.display = 'none';

  history = [];
  historySection.style.display = 'none';

  showStatus('info', '👋 You have been signed out successfully.');
}

function setLoggedInUI(userData) {

  document.getElementById('authButtons').style.display = 'none';

  const userMenu = document.getElementById('userMenu');
  userMenu.style.display = '';

  const name     = userData?.username || userData?.email?.split('@')[0] || 'User';
  const email    = userData?.email || '';
  const initial  = name.charAt(0).toUpperCase();

  document.getElementById('userAvatar').textContent      = initial;
  document.getElementById('userDisplayName').textContent = name;
  document.getElementById('dropdownName').textContent    = name;
  document.getElementById('dropdownEmail').textContent   = email;

  if (userData) {
    localStorage.setItem('vdl_user', JSON.stringify(userData));
  }

  const hKey = getHistoryKey();
  history = hKey ? JSON.parse(localStorage.getItem(hKey) || '[]') : [];
  renderHistory();
}

document.getElementById('loginSubmit').addEventListener('click', async () => {
  const email = document.getElementById('loginEmail').value.trim();
  const pass  = document.getElementById('loginPassword').value;

  if (!email) { alert('Please enter your email.'); return; }
  if (!pass)  { alert('Please enter your password.'); return; }

  try {
    const res  = await fetch(`${API}/auth/login`, {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ email, password: pass }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Login failed.');
    authToken = data.access_token;
    localStorage.setItem('vdl_token', authToken);
    authModal.classList.remove('show');

    // Fetch real username from backend — not just email prefix
    try {
      const meRes  = await fetch(`${API}/auth/me`, {
        headers: { Authorization: 'Bearer ' + authToken }
      });
      const meData = await meRes.json();
      setLoggedInUI(meData);
    } catch(e) {
      // Fallback if /me fails
      setLoggedInUI({ email: email, username: email.split('@')[0] });
    }
    showStatus('success', '✅ Welcome back!');
  } catch (e) {
    alert('Login error: ' + e.message);
  }
});

document.getElementById('registerSubmit').addEventListener('click', async () => {
  const email    = document.getElementById('regEmail').value.trim();
  const username = document.getElementById('regUsername').value.trim();
  const password = document.getElementById('regPassword').value;

  if (!email) {
    alert('❌ Please enter your email.'); return;
  }
  // Strict email format validation
  const emailRegex = /^[a-zA-Z0-9._%+\-]+@[a-zA-Z][a-zA-Z0-9.\-]*\.[a-zA-Z]{2,}$/;
  if (!emailRegex.test(email)) {
    alert('❌ Please enter a valid email address.'); return;
  }
  if (!username) {
    alert('❌ Please enter a username.'); return;
  }
  if (username.trim().length < 2) {
    alert('❌ Username must be at least 2 characters.'); return;
  }
  if (username.length > 50) {
    alert('❌ Username too long. Maximum 50 characters.'); return;
  }
  // Allow letters, numbers, dots, hyphens, underscores — NO spaces
  if (!/^[a-zA-Z0-9._\-]+$/.test(username)) {
    alert('❌ Username can only contain letters, numbers, dots (.), hyphens (-) and underscores (_).\n\nNo spaces allowed. Example: john_doe or john.doe'); return;
  }
  if (password.length < 8) {
    alert('❌ Password must be at least 8 characters.\n\nPlease use 8 or more characters.'); return;
  }
  if (password.length > 72) {
    alert('❌ Password is too long.\n\nMaximum allowed is 72 characters. Please shorten your password.'); return;
  }
  if (!/[A-Z]/.test(password)) {
    alert('❌ Password must contain at least one UPPERCASE letter.\n\nExample: Test1234'); return;
  }
  if (!/[0-9]/.test(password)) {
    alert('❌ Password must contain at least one number.\n\nExample: Test1234'); return;
  }

  try {
    const res  = await fetch(`${API}/auth/register`, {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ email, username, password }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Registration failed.');
    alert('✅ Account created successfully!\n\nPlease log in with your credentials.');
    loginForm.style.display = ''; registerForm.style.display = 'none';

    document.getElementById('loginEmail').value = email;
  } catch (e) {
    // Show clean error — never show [object Object]
    const msg = typeof e.message === 'string' ? e.message : 'Registration failed. Please try again.';
    alert('❌ ' + msg);
  }
});

document.getElementById('regPassword').addEventListener('input', function() {
  const val = this.value;
  const rules = [];
  if (val.length < 8)        rules.push('• At least 8 characters');
  if (val.length > 72)       rules.push('• Maximum 72 characters');
  if (!/[A-Z]/.test(val))    rules.push('• At least 1 uppercase letter');
  if (!/[0-9]/.test(val))    rules.push('• At least 1 number');

  let hint = document.getElementById('passwordHint');
  if (!hint) {
    hint = document.createElement('div');
    hint.id = 'passwordHint';
    hint.style.cssText = 'font-size:11px;margin-top:6px;line-height:1.7;';
    this.parentNode.appendChild(hint);
  }
  if (rules.length > 0 && val.length > 0) {
    hint.style.color = 'var(--red)';
    hint.innerHTML = rules.join('<br>');
  } else if (val.length > 0) {
    hint.style.color = 'var(--green)';
    hint.innerHTML = '✅ Password looks good!';
  } else {
    hint.innerHTML = '';
  }
});

let dlFilter  = 'all';
let dlSearch  = '';

const PLATFORM_ICONS = {
  youtube:'▶️', instagram:'📸', twitter:'🐦',
  facebook:'📘', reddit:'🤖',
  direct:'🔗', image:'🖼️', video:'🎬', audio:'🎵',
  document:'📄', webpage:'🌐', unknown:'🔗'
};

let _dlPanelJustOpened = false;

function openDlPanel(e) {
  if (e) e.stopPropagation();

  closeUserMenu();

  if (!authToken) return;

  const overlay = document.getElementById('dlPanelOverlay');
  if (overlay) {
    overlay.classList.add('open');
    renderDlPanel();
  }
}

function closeDlPanel(e) {

  const panel = document.getElementById('dlPanel');
  if (e && panel && panel.contains(e.target)) return;
  closeDlPanelBtn();
}

function closeDlPanelBtn() {
  document.getElementById('dlPanelOverlay').classList.remove('open');
  document.body.style.overflow = '';
}

function setDlFilter(filter, btn) {
  dlFilter = filter;
  document.querySelectorAll('.dl-filter-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  renderDlItems();
}

function filterDownloads() {
  dlSearch = document.getElementById('dlSearchInput').value.toLowerCase();
  renderDlItems();
}

function clearAllDownloads() {
  if (!confirm('Clear all download history? This cannot be undone.')) return;
  history = [];
  localStorage.setItem(getHistoryKey(), '[]');
  renderDlPanel();
  renderHistory();
}

function formatBytes(bytes) {
  if (!bytes || bytes === 0) return '';
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024*1024) return (bytes/1024).toFixed(1) + ' KB';
  return (bytes/(1024*1024)).toFixed(1) + ' MB';
}

function timeAgoFull(ts) {
  const s = Math.floor((Date.now() - ts) / 1000);
  if (s < 60)   return 'Just now';
  if (s < 3600)  return Math.floor(s/60) + ' min ago';
  if (s < 86400) return Math.floor(s/3600) + ' hr ago';
  if (s < 604800) return Math.floor(s/86400) + ' days ago';
  return new Date(ts).toLocaleDateString();
}

function getMediaBadge(item) {
  const t = (item.media_type || item.platform || '').toLowerCase();
  if (t.includes('video') || t.includes('youtube') || t.includes('instagram')) return 'video';
  if (t.includes('audio') || t.includes('mp3')) return 'audio';
  if (t.includes('image') || t.includes('png') || t.includes('jpg')) return 'image';
  if (t.includes('document') || t.includes('pdf')) return 'document';
  return 'video';
}

function renderDlPanel() {

  const total    = history.length;
  const videos   = history.filter(h => getMediaBadge(h) === 'video').length;
  const images   = history.filter(h => getMediaBadge(h) === 'image').length;
  const docs     = history.filter(h => getMediaBadge(h) === 'document').length;

  document.getElementById('dlStats').innerHTML = `
    <div class="dl-stat">
      <div class="dl-stat-num">${total}</div>
      <div class="dl-stat-label">Total</div>
    </div>
    <div class="dl-stat">
      <div class="dl-stat-num">${videos}</div>
      <div class="dl-stat-label">Videos</div>
    </div>
    <div class="dl-stat">
      <div class="dl-stat-num">${images + docs}</div>
      <div class="dl-stat-label">Files</div>
    </div>
  `;

  renderDlItems();
}

function renderDlItems() {
  const list    = document.getElementById('dlItemsList');
  const counter = document.getElementById('dlCountText');
  const section = document.getElementById('dlSectionTitle');

  let items = [...history];

  if (dlFilter !== 'all') {
    items = items.filter(h => {
      const p = (h.platform || '').toLowerCase();
      const t = (h.media_type || '').toLowerCase();
      if (dlFilter === 'video')    return getMediaBadge(h) === 'video';
      if (dlFilter === 'image')    return getMediaBadge(h) === 'image';
      if (dlFilter === 'document') return getMediaBadge(h) === 'document';
      return p.includes(dlFilter);
    });
  }

  if (dlSearch) {
    items = items.filter(h =>
      (h.title || h.url || '').toLowerCase().includes(dlSearch) ||
      (h.platform || '').toLowerCase().includes(dlSearch)
    );
  }

  counter.textContent = `${items.length} download${items.length !== 1 ? 's' : ''}`;
  section.textContent = dlSearch ? `Search results (${items.length})` :
                        dlFilter !== 'all' ? `${dlFilter.charAt(0).toUpperCase()+dlFilter.slice(1)} downloads` :
                        'Recent Downloads';

  if (items.length === 0) {
    list.innerHTML = `
      <div class="dl-empty">
        <div class="dl-empty-icon">📭</div>
        <div class="dl-empty-title">${dlSearch ? 'No results found' : 'No downloads yet'}</div>
        <div class="dl-empty-sub">${dlSearch ? 'Try a different search term' : 'Start downloading media and your history will appear here.'}</div>
      </div>`;
    return;
  }

  list.innerHTML = items.map((h, i) => {
    const platform  = (h.platform || 'unknown').toLowerCase();
    const icon      = PLATFORM_ICONS[platform] || PLATFORM_ICONS[getMediaBadge(h)] || '🔗';
    const badge     = getMediaBadge(h);
    const title     = h.title || h.url?.split('/').pop() || 'Unknown';
    const timeStr   = timeAgoFull(h.time);
    const sizeStr   = formatBytes(h.file_size);
    const shortUrl  = (h.url || '').replace(/^https?:\/\/(www\.)?/, '').substring(0, 40);

    return `
    <div class="dl-item" onclick="reFetchFromPanel('${h.url}')">
      <div class="dl-item-icon">${icon}</div>
      <div class="dl-item-info">
        <div class="dl-item-title" title="${title}">${title}</div>
        <div class="dl-item-meta">
          <span class="dl-item-platform">${platform}</span>
          <span class="dl-item-time">${timeStr}</span>
          ${sizeStr ? `<span class="dl-item-size">${sizeStr}</span>` : ''}
        </div>
        <div style="font-size:11px;color:var(--text-3);margin-top:3px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${shortUrl}</div>
      </div>
      <span class="dl-item-badge ${badge}">${badge.toUpperCase()}</span>
      <button class="dl-item-refetch" title="Re-fetch this URL" onclick="event.stopPropagation();reFetchFromPanel('${h.url}')">↩</button>
    </div>`;
  }).join('');
}

function reFetchFromPanel(url) {
  closeDlPanelBtn();
  urlInput.value = url;
  urlInput.dispatchEvent(new Event('input'));
  window.scrollTo({ top: 0, behavior: 'smooth' });
  setTimeout(() => analyzeBtn.click(), 300);
}

function _hideAllForms() {
  ['loginForm','forgotForm','resetForm','newPasswordForm','registerForm'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.style.display = 'none';
  });
}

function showForgotForm() {
  _hideAllForms();
  _clearResetFields();
  document.getElementById('forgotForm').style.display = '';

  // Always clear email field — never pre-fill
  const fe = document.getElementById('forgotEmail');
  if (fe) fe.value = '';

  // Always clear error box
  const errBox = document.getElementById('forgotEmailError');
  if (errBox) { errBox.style.display = 'none'; errBox.textContent = ''; }

  // Always clear success box
  const fs = document.getElementById('forgotSuccess');
  if (fs) fs.style.display = 'none';

  // Reset button to original state
  const fb = document.getElementById('forgotSubmit');
  if (fb) { fb.textContent = 'Send reset code'; fb.disabled = false; }
}

function _clearResetFields() {
  ['otp1','otp2','otp3','otp4','otp5','otp6'].forEach(id => {
    const el = document.getElementById(id); if (el) el.value = '';
  });
  ['newPassword','confirmPassword'].forEach(id => {
    const el = document.getElementById(id); if (el) el.value = '';
  });
  const sf = document.getElementById('strengthFill'); if (sf) sf.style.width = '0';
  const st = document.getElementById('strengthText'); if (st) st.textContent = '';
  const errEl = document.getElementById('otpError'); if (errEl) errEl.style.display = 'none';
  const btn = document.getElementById('verifyOtpBtn');
  if (btn) { btn.textContent = 'Verify code →'; btn.disabled = false; }
}

function showLoginForm() {
  _hideAllForms();
  _clearResetFields();
  document.getElementById('loginForm').style.display = '';

  // Clear forgot form errors too
  const errBox = document.getElementById('forgotEmailError');
  if (errBox) { errBox.style.display = 'none'; errBox.textContent = ''; }
  const fe = document.getElementById('forgotEmail');
  if (fe) fe.value = '';
  const fs = document.getElementById('forgotSuccess');
  if (fs) fs.style.display = 'none';
  const fb = document.getElementById('forgotSubmit');
  if (fb) { fb.textContent = 'Send reset code'; fb.disabled = false; }
}

async function sendResetCode() {
  const email = document.getElementById('forgotEmail').value.trim();
  const errBox = document.getElementById('forgotEmailError');

  if (!email) {
    if (errBox) { errBox.textContent = 'Please enter your email address.'; errBox.style.display = 'block'; }
    return;
  }

  const emailRe = /^[a-zA-Z0-9._%+\-]+@[a-zA-Z][a-zA-Z0-9.\-]*\.[a-zA-Z]{2,}$/;
  if (!emailRe.test(email)) {
    if (errBox) { errBox.textContent = '❌ Invalid email format. Example: name@gmail.com'; errBox.style.display = 'block'; }
    return;
  }

  if (errBox) errBox.style.display = 'none';

  const btn = document.getElementById('forgotSubmit');
  btn.textContent = '⏳ Sending...';
  btn.disabled = true;

  try {
    const res  = await fetch(`${API}/auth/forgot-password`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ email }),
    });
    const data = await res.json();

    if (data.sent === false) {

      if (errBox) {
        errBox.textContent = '❌ No account found with this email. Please check or sign up first.';
        errBox.style.display = 'block';
      }
      btn.textContent = 'Send reset code';
      btn.disabled = false;
      return;
    }

    document.getElementById('forgotSuccess').style.display = 'block';
    btn.textContent = 'Resend code';
    btn.disabled = false;

    setTimeout(() => {
      _hideAllForms();
      _clearResetFields();
      document.getElementById('resetForm').style.display = '';
      const o1 = document.getElementById('otp1');
      if (o1) o1.focus();
    }, 2000);

  } catch(e) {
    if (errBox) { errBox.textContent = 'Could not send reset code. Please try again.'; errBox.style.display = 'block'; }
    btn.textContent = 'Send reset code';
    btn.disabled = false;
  }
}

function otpMove(current, nextId) {
  if (current.value.length === 1 && nextId) {
    const next = document.getElementById(nextId);
    if (next) next.focus();
  }
}

function resendCode() {

  ['otp1','otp2','otp3','otp4','otp5','otp6'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.value = '';
  });

  const errEl = document.getElementById('otpError');
  if (errEl) errEl.style.display = 'none';

  const btn = document.getElementById('verifyOtpBtn');
  if (btn) { btn.textContent = 'Verify code →'; btn.disabled = false; }

  showForgotForm();
}

function autoVerifyOtp() {

  const otp = ['otp1','otp2','otp3','otp4','otp5','otp6'].map(id => document.getElementById(id).value).join('');
  if (otp.length === 6) {
    setTimeout(() => verifyOtp(), 300);
  }
}

async function verifyOtp() {
  const otp   = ['otp1','otp2','otp3','otp4','otp5','otp6'].map(id => document.getElementById(id).value).join('');
  const email = document.getElementById('forgotEmail').value.trim();
  const errEl = document.getElementById('otpError');
  const btn   = document.getElementById('verifyOtpBtn');

  if (otp.length < 6) {
    errEl.textContent = 'Please enter the complete 6-digit code.';
    errEl.style.display = 'block';
    return;
  }

  btn.textContent = 'Verifying...';
  btn.disabled    = true;
  errEl.style.display = 'none';

  try {
    const res  = await fetch(`${API}/auth/verify-otp`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ email, otp }),
    });
    const data = await res.json();

    if (res.ok && data.valid) {

      _hideAllForms();
      document.getElementById('newPasswordForm').style.display = '';
    } else {

      errEl.textContent = data.detail || '❌ Invalid code. Please check and try again.';
      errEl.style.display = 'block';

      document.querySelector('.otp-inputs').style.animation = 'shake 0.4s ease';
      setTimeout(() => document.querySelector('.otp-inputs').style.animation = '', 500);
      btn.textContent = 'Verify code →';
      btn.disabled    = false;
    }
  } catch(e) {
    errEl.textContent = '❌ Could not verify code. Please try again.';
    errEl.style.display = 'block';
    btn.textContent = 'Verify code →';
    btn.disabled    = false;
  }
}

function otpBack(e, prevId) {
  if (e.key === 'Backspace' && e.target.value === '' && prevId) {
    const prev = document.getElementById(prevId);
    if (prev) { prev.focus(); prev.value = ''; }
  }
}

function checkNewPasswordStrength(val) {
  const fill = document.getElementById('strengthFill');
  const text = document.getElementById('strengthText');
  if (!val) { fill.style.width='0'; text.textContent=''; return; }

  let score = 0;
  if (val.length >= 8)          score++;
  if (/[A-Z]/.test(val))        score++;
  if (/[0-9]/.test(val))        score++;
  if (/[^A-Za-z0-9]/.test(val)) score++;

  const levels = [
    { w:'25%', color:'#f87171', label:'Weak' },
    { w:'50%', color:'#fb923c', label:'Fair' },
    { w:'75%', color:'#fbbf24', label:'Good' },
    { w:'100%',color:'#34d399', label:'Strong ✅' },
  ];
  const lv = levels[score - 1] || levels[0];
  fill.style.width  = lv.w;
  fill.style.background = lv.color;
  text.style.color  = lv.color;
  text.textContent  = lv.label;
}

async function resetPassword() {
  const otp     = ['otp1','otp2','otp3','otp4','otp5','otp6'].map(id => document.getElementById(id).value).join('');
  const newPass = document.getElementById('newPassword').value;
  const confirm = document.getElementById('confirmPassword').value;
  const email   = document.getElementById('forgotEmail').value.trim();

  if (newPass.length < 8)     { alert('Password must be at least 8 characters.'); return; }
  if (!/[A-Z]/.test(newPass)) { alert('Password must contain at least 1 uppercase letter.'); return; }
  if (!/[0-9]/.test(newPass)) { alert('Password must contain at least 1 number.'); return; }
  if (newPass !== confirm)     { alert('Passwords do not match.'); return; }

  try {
    const res  = await fetch(`${API}/auth/reset-password`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ email, otp, new_password: newPass }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Reset failed.');

    _hideAllForms();
    document.getElementById('loginForm').style.display = '';
    document.getElementById('loginEmail').value = email;

    const sub = document.querySelector('#loginForm .modal-sub');
    if (sub) {
      sub.innerHTML = '<span style="color:var(--green)">✅ Password reset! Log in with your new password.</span>';
      setTimeout(() => { sub.innerHTML = 'Log in to access download history and API keys.'; }, 5000);
    }
  } catch(e) {
    alert('❌ ' + e.message);
  }
}

let settingsPrefs = JSON.parse(localStorage.getItem('vdl_prefs') || '{}');
let selectedAvatarColor = localStorage.getItem('vdl_avatar_color') || '#fbbf24';

function openSettings(e) {
  if (e) e.stopPropagation();
  closeUserMenu();
  if (!authToken) return;
  const overlay = document.getElementById('settingsOverlay');
  if (overlay) {
    overlay.classList.add('open');
    loadSettingsData();
  }
}

function closeSettings() {
  const overlay = document.getElementById('settingsOverlay');
  if (overlay) overlay.classList.remove('open');
}

window.addEventListener('load', function() {
  const so = document.getElementById('settingsOverlay');
  if (so) so.addEventListener('click', function(e) {
    if (e.target === this) closeSettings();
  });
});

function switchTab(tabName, btn) {

  document.querySelectorAll('.settings-section').forEach(s => s.classList.remove('active'));
  document.querySelectorAll('.settings-tab').forEach(b => b.classList.remove('active'));

  const sec = document.getElementById('tab-' + tabName);
  if (sec) sec.classList.add('active');
  if (btn) btn.classList.add('active');
}

function loadSettingsData() {
  const user = JSON.parse(localStorage.getItem('vdl_user') || '{}');
  const name  = user.username || user.email?.split('@')[0] || 'User';
  const email = user.email || '';

  const el = (id) => document.getElementById(id);
  if (el('displayUsername')) el('displayUsername').textContent = name;
  if (el('displayEmail'))    el('displayEmail').textContent    = email;
  if (el('displayJoined'))   el('displayJoined').textContent   = 'Recently';
  if (el('displayDownloads'))el('displayDownloads').textContent= history.length;
  if (el('newUsername'))     el('newUsername').value           = name;

  if (el('previewAvatar')) {
    el('previewAvatar').textContent    = name.charAt(0).toUpperCase();
    el('previewAvatar').style.background = selectedAvatarColor;
  }
  if (el('previewName'))  el('previewName').textContent  = name;
  if (el('previewEmail')) el('previewEmail').textContent = email;

  document.querySelectorAll('.avatar-color').forEach(el => {
    el.textContent = name.charAt(0).toUpperCase();
    el.classList.toggle('selected', el.dataset.color === selectedAvatarColor);
  });

  if (el('prefQuality'))    el('prefQuality').value   = settingsPrefs.quality    || 'best';
  if (el('prefFormat'))     el('prefFormat').value    = settingsPrefs.format     || 'auto';
  if (el('prefHistory'))    el('prefHistory').checked = settingsPrefs.history    !== false;
  if (el('prefNotify'))     el('prefNotify').checked  = settingsPrefs.notify     !== false;
  if (el('prefAutoDetect')) el('prefAutoDetect').checked = settingsPrefs.autoDetect !== false;

  if (el('appearTheme')) el('appearTheme').checked = isDark;

  if (el('lastLogin')) el('lastLogin').textContent = new Date().toLocaleString();
}

function toggleEditField(field) {
  const el = document.getElementById('edit' + field.charAt(0).toUpperCase() + field.slice(1));
  if (el) el.style.display = el.style.display === 'none' ? '' : 'none';
}

async function saveUsername() {
  const newName = document.getElementById('newUsername').value.trim();
  if (!newName || newName.length < 3) {
    alert('Username must be at least 3 characters.'); return;
  }

  const user = JSON.parse(localStorage.getItem('vdl_user') || '{}');
  user.username = newName;
  localStorage.setItem('vdl_user', JSON.stringify(user));

  document.getElementById('displayUsername').textContent = newName;
  document.getElementById('userDisplayName').textContent = newName;
  document.getElementById('dropdownName').textContent    = newName;
  document.getElementById('userAvatar').textContent      = newName.charAt(0).toUpperCase();
  document.getElementById('previewName').textContent     = newName;
  document.getElementById('editUsername').style.display  = 'none';

  showSettingsSuccess('✅ Username updated!');
}

function selectAvatarColor(el) {
  document.querySelectorAll('.avatar-color').forEach(a => a.classList.remove('selected'));
  el.classList.add('selected');
  selectedAvatarColor = el.dataset.color;
  localStorage.setItem('vdl_avatar_color', selectedAvatarColor);

  document.getElementById('previewAvatar').style.background = selectedAvatarColor;
  document.getElementById('userAvatar').style.background    = selectedAvatarColor;
  showSettingsSuccess('✅ Avatar color saved!');
}

function checkSecPasswordStrength(val) {
  const fill = document.getElementById('secStrengthFill');
  const text = document.getElementById('secStrengthText');
  if (!fill) return;
  if (!val) { fill.style.width='0'; text.textContent=''; return; }
  let score = 0;
  if (val.length >= 8)          score++;
  if (/[A-Z]/.test(val))        score++;
  if (/[0-9]/.test(val))        score++;
  if (/[^A-Za-z0-9]/.test(val)) score++;
  const levels = [
    {w:'25%',color:'#f87171',label:'Weak'},
    {w:'50%',color:'#fb923c',label:'Fair'},
    {w:'75%',color:'#fbbf24',label:'Good'},
    {w:'100%',color:'#34d399',label:'Strong ✅'},
  ];
  const lv = levels[score-1] || levels[0];
  fill.style.width = lv.w;
  fill.style.background = lv.color;
  text.style.color = lv.color;
  text.textContent = lv.label;
}

async function changePassword() {
  const current = document.getElementById('currentPass').value;
  const newPass  = document.getElementById('secNewPass').value;
  const confirm  = document.getElementById('secConfirmPass').value;

  if (!current)               { alert('Please enter your current password.'); return; }
  if (newPass.length < 8)     { alert('New password must be at least 8 characters.'); return; }
  if (!/[A-Z]/.test(newPass)) { alert('Password must have at least 1 uppercase letter.'); return; }
  if (!/[0-9]/.test(newPass)) { alert('Password must have at least 1 number.'); return; }
  if (newPass !== confirm)     { alert('Passwords do not match.'); return; }

  try {
    const res = await fetch(`${API}/auth/change-password`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${authToken}`
      },
      body: JSON.stringify({ current_password: current, new_password: newPass }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Failed to change password.');
    document.getElementById('currentPass').value   = '';
    document.getElementById('secNewPass').value    = '';
    document.getElementById('secConfirmPass').value= '';
    showSettingsSuccess('✅ Password changed successfully!');
  } catch(e) {
    alert('❌ ' + e.message);
  }
}

function savePref(key, value) {
  settingsPrefs[key] = value;
  localStorage.setItem('vdl_prefs', JSON.stringify(settingsPrefs));
  showSettingsSuccess('✅ Preference saved!');
}

function toggleThemeFromSettings(checked) {
  isDark = checked;
  applyTheme();
  showSettingsSuccess('✅ Theme updated!');
}

function setAccent(el, color, hover) {
  document.querySelectorAll('.accent-dot').forEach(d => d.classList.remove('selected'));
  el.classList.add('selected');
  document.documentElement.style.setProperty('--amber', color);
  localStorage.setItem('vdl_accent', color);
  showSettingsSuccess('✅ Accent color applied!');
}

function clearHistoryFromSettings() {
  if (!confirm('Clear all download history? This cannot be undone.')) return;
  history = [];
  const key = getHistoryKey();
  if (key) localStorage.setItem(key, '[]');
  renderHistory();
  document.getElementById('displayDownloads').textContent = '0';
  showSettingsSuccess('✅ History cleared!');
}

async function deleteAccount() {
  const input = document.getElementById('deleteConfirmInput').value.trim();
  if (input !== 'DELETE') {
    alert('Please type DELETE exactly to confirm account deletion.'); return;
  }
  if (!confirm('This will permanently delete your account. Are you absolutely sure?')) return;

  try {
    const res = await fetch(`${API}/auth/delete-account`, {
      method: 'DELETE',
      headers: { 'Authorization': `Bearer ${authToken}` },
    });
    if (!res.ok) throw new Error('Could not delete account.');
    closeSettings();
    handleLogout();
    alert('Your account has been deleted.');
  } catch(e) {
    alert('❌ ' + e.message);
  }
}

function showSettingsSuccess(msg) {
  showStatus('success', msg);
}

const savedAccent = localStorage.getItem('vdl_accent');
if (savedAccent) document.documentElement.style.setProperty('--amber', savedAccent);

const savedAvatarColor = localStorage.getItem('vdl_avatar_color');
if (savedAvatarColor) {
  const av = document.getElementById('userAvatar');
  if (av) av.style.background = savedAvatarColor;
}

function openSettings(e) {
  if (e) e.stopPropagation();
  closeUserMenu();
  if (!authToken) return;
  const overlay = document.getElementById('settingsOverlay');
  if (overlay) {
    overlay.classList.add('open');
    loadSettingsData();
  }
}

function closeSettings() {
  const overlay = document.getElementById('settingsOverlay');
  if (overlay) overlay.classList.remove('open');
}

window.addEventListener('load', function() {
  const so = document.getElementById('settingsOverlay');
  if (so) so.addEventListener('click', function(e) {
    if (e.target === this) closeSettings();
  });
});

function switchTab(name, btn) {

  document.querySelectorAll('.settings-tab-content').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.settings-tab').forEach(t => t.classList.remove('active'));

  const tab = document.getElementById('tab-' + name);
  if (tab) tab.classList.add('active');
  if (btn) btn.classList.add('active');
}

function loadSettingsData() {
  const user = JSON.parse(localStorage.getItem('vdl_user') || '{}');
  const name  = user.username || user.email?.split('@')[0] || 'User';
  const email = user.email || '';
  const color = localStorage.getItem('vdl_avatar_color') || '#fbbf24';

  document.getElementById('settingsAvatar').textContent = name.charAt(0).toUpperCase();
  document.getElementById('settingsAvatar').style.background = color;
  document.getElementById('settingsName').textContent  = name;
  document.getElementById('settingsEmail').textContent = email;
  document.getElementById('settingsSince').textContent = 'Member since ' + new Date().getFullYear();
  document.getElementById('editUsername').value = name;
  document.getElementById('editEmail').value    = email;
  document.getElementById('sessionEmail').textContent = email;

  const total     = history.length;
  const videos    = history.filter(h => (h.media_type||'').includes('video')).length;
  const platforms = new Set(history.map(h => h.platform)).size;
  document.getElementById('statTotal').textContent     = total;
  document.getElementById('statVideos').textContent    = videos;
  document.getElementById('statPlatforms').textContent = platforms;

  document.querySelectorAll('.color-dot').forEach(d => {
    d.classList.toggle('selected', d.dataset.color === color);
  });

  const prefs = settingsPrefs;
  const quality = prefs.quality || 'best';
  const format  = prefs.format  || 'auto';
  document.querySelectorAll('#qualityOptions .option-chip').forEach(c => {
    c.classList.toggle('selected', c.dataset.val === quality);
  });
  document.querySelectorAll('#formatOptions .option-chip').forEach(c => {
    c.classList.toggle('selected', c.dataset.val === format);
  });
  if (document.getElementById('toggleHistory'))
    document.getElementById('toggleHistory').checked = prefs.saveHistory !== false;
  if (document.getElementById('toggleDetect'))
    document.getElementById('toggleDetect').checked = prefs.autoDetect !== false;
  if (document.getElementById('toggleSize'))
    document.getElementById('toggleSize').checked = prefs.showSize !== false;

  const theme = localStorage.getItem('vdl_theme') || 'dark';
  document.querySelectorAll('[id^="theme"]').forEach(el => el.classList.remove('selected'));
  const themeEl = document.getElementById('theme' + theme.charAt(0).toUpperCase() + theme.slice(1));
  if (themeEl) themeEl.classList.add('selected');

  const accent = localStorage.getItem('vdl_accent') || '#fbbf24';
  document.querySelectorAll('.accent-chip').forEach(c => {
    c.classList.toggle('selected', c.dataset.accent === accent);
  });
}

function setAvatarColor(color, dot) {
  localStorage.setItem('vdl_avatar_color', color);
  document.getElementById('settingsAvatar').style.background = color;
  document.getElementById('userAvatar').style.background = color;
  document.querySelectorAll('.color-dot').forEach(d => d.classList.remove('selected'));
  dot.classList.add('selected');
}

function saveProfile() {
  const username = document.getElementById('editUsername').value.trim();
  if (!username) { alert('Username cannot be empty.'); return; }
  if (username.length < 3) { alert('Username must be at least 3 characters.'); return; }

  const user = JSON.parse(localStorage.getItem('vdl_user') || '{}');
  user.username = username;
  localStorage.setItem('vdl_user', JSON.stringify(user));

  document.getElementById('settingsName').textContent  = username;
  document.getElementById('userDisplayName').textContent = username;
  document.getElementById('dropdownName').textContent  = username;
  document.getElementById('userAvatar').textContent    = username.charAt(0).toUpperCase();

  showStatus('success', '✅ Profile updated successfully!');
  showSettingsToast('Profile saved!');
}

function settingsPwStrength(val) {
  const fill = document.getElementById('settingsPwFill');
  const text = document.getElementById('settingsPwText');
  if (!val || !fill) return;
  let score = 0;
  if (val.length >= 8)          score++;
  if (/[A-Z]/.test(val))        score++;
  if (/[0-9]/.test(val))        score++;
  if (/[^A-Za-z0-9]/.test(val)) score++;
  const levels = [
    { w:'25%', c:'#f87171', l:'Weak' },
    { w:'50%', c:'#fb923c', l:'Fair' },
    { w:'75%', c:'#fbbf24', l:'Good' },
    { w:'100%',c:'#34d399', l:'Strong ✅' },
  ];
  const lv = levels[score-1] || levels[0];
  fill.style.width = lv.w;
  fill.style.background = lv.c;
  text.style.color = lv.c;
  text.textContent = lv.l;
}

async function changePassword() {
  const current = document.getElementById('currentPw').value;
  const newPw   = document.getElementById('newPw').value;
  const confirm = document.getElementById('confirmPw').value;

  if (!current) { alert('Please enter your current password.'); return; }
  if (newPw.length < 8)     { alert('New password must be at least 8 characters.'); return; }
  if (!/[A-Z]/.test(newPw)) { alert('New password must contain at least 1 uppercase letter.'); return; }
  if (!/[0-9]/.test(newPw)) { alert('New password must contain at least 1 number.'); return; }
  if (newPw !== confirm)     { alert('Passwords do not match.'); return; }

  try {
    const res = await fetch(`${API}/auth/change-password`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${authToken}`
      },
      body: JSON.stringify({ current_password: current, new_password: newPw }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Failed to change password.');
    document.getElementById('currentPw').value = '';
    document.getElementById('newPw').value     = '';
    document.getElementById('confirmPw').value = '';
    showSettingsToast('Password updated!');
    showStatus('success', '✅ Password changed successfully!');
  } catch(e) {
    alert('❌ ' + e.message);
  }
}

function selectOption(type, val, el) {
  const container = type === 'quality' ? 'qualityOptions' : 'formatOptions';
  document.querySelectorAll('#' + container + ' .option-chip').forEach(c => c.classList.remove('selected'));
  el.classList.add('selected');
  settingsPrefs[type] = val;
  savePrefs();
}

function savePrefs() {
  settingsPrefs.saveHistory = document.getElementById('toggleHistory')?.checked !== false;
  settingsPrefs.autoDetect  = document.getElementById('toggleDetect')?.checked !== false;
  settingsPrefs.showSize    = document.getElementById('toggleSize')?.checked !== false;
  localStorage.setItem('vdl_prefs', JSON.stringify(settingsPrefs));
  showSettingsToast('Preferences saved!');
}

function setThemeMode(mode, el) {
  document.querySelectorAll('[id^="theme"]').forEach(e => e.classList.remove('selected'));
  el.classList.add('selected');
  if (mode === 'system') {
    isDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
  } else {
    isDark = mode === 'dark';
  }
  applyTheme();
  localStorage.setItem('vdl_theme_mode', mode);
}

function setAccentColor(color, el) {
  document.querySelectorAll('.accent-chip').forEach(c => c.classList.remove('selected'));
  el.classList.add('selected');
  localStorage.setItem('vdl_accent', color);
  document.documentElement.style.setProperty('--amber', color);
  document.documentElement.style.setProperty('--amber-dim', color + '20');
  document.documentElement.style.setProperty('--border-hi', color + '4d');
  document.documentElement.style.setProperty('--glow-a', color + '33');
  showSettingsToast('Accent color applied!');
}

function applyCompact(on) {
  document.body.style.setProperty('--radius', on ? '10px' : '16px');
  localStorage.setItem('vdl_compact', on ? '1' : '0');
}

function applyAnimations(on) {
  document.body.style.setProperty('--transition', on ? 'all 0.2s' : 'none');
  localStorage.setItem('vdl_animations', on ? '1' : '0');
}

function clearHistoryFromSettings() {
  if (!confirm('Clear all download history? This cannot be undone.')) return;
  history = [];
  const key = getHistoryKey();
  if (key) localStorage.setItem(key, '[]');
  renderHistory();
  loadSettingsData();
  showSettingsToast('History cleared!');
}

async function deleteAccount() {
  const email    = document.getElementById('deleteConfirmEmail').value.trim();
  const user     = JSON.parse(localStorage.getItem('vdl_user') || '{}');
  const expected = user.email || '';

  if (!email) { alert('Please enter your email to confirm.'); return; }
  if (email.toLowerCase() !== expected.toLowerCase()) {
    alert('Email does not match your account email.'); return;
  }
  if (!confirm('Are you absolutely sure? This will permanently delete your account and all data.')) return;

  try {
    const res = await fetch(`${API}/auth/delete-account`, {
      method: 'DELETE',
      headers: { 'Authorization': `Bearer ${authToken}` },
    });
    if (res.ok || res.status === 204) {
      handleLogout();
      closeSettings();
      showStatus('info', '👋 Your account has been deleted.');
    } else {
      const d = await res.json().catch(() => ({}));
      alert('❌ ' + (d.detail || 'Could not delete account.'));
    }
  } catch(e) {

    handleLogout();
    closeSettings();
  }
}

function showSettingsToast(msg) {
  let toast = document.getElementById('settingsToast');
  if (!toast) {
    toast = document.createElement('div');
    toast.id = 'settingsToast';
    toast.style.cssText = `
      position:fixed;bottom:24px;right:24px;
      background:var(--green);color:#0c0c0f;
      padding:10px 18px;border-radius:10px;
      font-size:13px;font-weight:700;z-index:9999;
      opacity:0;transform:translateY(10px);
      transition:all 0.3s;pointer-events:none;
    `;
    document.body.appendChild(toast);
  }
  toast.textContent = '✅ ' + msg;
  toast.style.opacity = '1';
  toast.style.transform = 'translateY(0)';
  clearTimeout(toast._timer);
  toast._timer = setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateY(10px)';
  }, 2500);
}

(function applyAccentOnLoad() {
  const accent = localStorage.getItem('vdl_accent');
  if (accent && accent !== '#fbbf24') {
    document.documentElement.style.setProperty('--amber', accent);
    document.documentElement.style.setProperty('--amber-dim', accent + '20');
    document.documentElement.style.setProperty('--border-hi', accent + '4d');
    document.documentElement.style.setProperty('--glow-a', accent + '33');
  }
  const avatarColor = localStorage.getItem('vdl_avatar_color');
  if (avatarColor) {
    const av = document.getElementById('userAvatar');
    if (av) av.style.background = avatarColor;
  }
})();

const FAQ_DATA = [
  {
    q: "How to download Instagram Reels for free?",
    a: `<strong>Step 1:</strong> Open Instagram → Find the Reel → Tap ⋯ → <strong>Copy Link</strong><br>
<strong>Step 2:</strong> Paste the link here → Click <strong>Fetch</strong><br>
<strong>Step 3:</strong> Click <strong>Download MP4</strong> — saves to your phone instantly!<br><br>
Works on Android, iPhone, PC — completely free, no watermark, no app needed.`
  },
  {
    q: "Can I download Instagram Reels without watermark?",
    a: `<strong>Yes! 100% without watermark.</strong><br><br>
VideoDL downloads directly from Instagram's servers. Your downloaded video will have:<br>
✅ No watermark or logo<br>
✅ Original quality (up to 1080p)<br>
✅ Original audio intact<br>
✅ MP4 format — plays on all devices`
  },
  {
    q: "How to download Instagram Reel on Android phone?",
    a: `<strong>Step 1:</strong> Open Instagram → Find the Reel<br>
<strong>Step 2:</strong> Tap ⋯ → <strong>Copy Link</strong><br>
<strong>Step 3:</strong> Open Chrome → Go to this website<br>
<strong>Step 4:</strong> Paste link → Click Fetch → Click Download MP4<br>
<strong>Step 5:</strong> Video saves to your <strong>Downloads folder</strong><br><br>
Works on Samsung, Redmi, Realme, OnePlus, Vivo, Oppo and all Android phones.`
  },
  {
    q: "Is VideoDL safe to use?",
    a: `<strong>Yes, completely safe!</strong><br><br>
🔒 We never ask for your Instagram or YouTube password<br>
🔒 We don't store your downloaded files<br>
🔒 No malware or suspicious software<br>
🔒 HTTPS encrypted — all connections are secure<br>
🔒 No spam emails or notifications`
  },
  {
    q: "What platforms are supported?",
    a: `VideoDL supports:<br><br>
📸 <strong>Instagram</strong> — Reels, posts, carousels<br>
▶️ <strong>YouTube</strong> — Videos, Shorts, MP3 audio<br>
📘 <strong>Facebook</strong> — Videos and posts<br>
🐦 <strong>Twitter/X</strong> — Videos and GIFs<br>
🤖 <strong>Reddit</strong> — Videos, images, GIFs<br>
🖼️ <strong>Direct files</strong> — JPG, PNG, MP4, PDF, MP3`
  },
];

function onQualityChange() {
  // Re-render results with new quality filter if results are showing
  if (resultCard.classList.contains('show') && window._lastResultData) {
    renderResults(window._lastResultData, window._lastSourceUrl);
  }
}

function validateUsernameField(input) {
  const val = input.value;
  const hint = document.getElementById('usernameHint');
  if (!hint) return;

  if (!val) {
    hint.style.color = 'var(--text-3)';
    hint.textContent = "Only letters, numbers, dots (.), hyphens (-), underscores (_). No spaces.";
    return;
  }
  if (val.length < 2) {
    hint.style.color = 'var(--red)';
    hint.textContent = '❌ Too short — minimum 2 characters.';
    return;
  }
  if (/\s/.test(val)) {
    hint.style.color = 'var(--red)';
    hint.textContent = '❌ Spaces not allowed. Use underscore instead: john_doe';
    return;
  }
  if (!/^[a-zA-Z0-9._\-]+$/.test(val)) {
    hint.style.color = 'var(--red)';
    hint.textContent = '❌ Only letters, numbers, dots (.), hyphens (-) and underscores (_) allowed.';
    return;
  }
  hint.style.color = 'var(--green)';
  hint.textContent = '✅ Username looks good!';
}

function subscribeNewsletter(btn) {
  const input = btn.previousElementSibling || document.getElementById('footerEmailInput');
  const email = input ? input.value.trim() : '';
  const emailRe = /^[a-zA-Z0-9._%+\-]+@[a-zA-Z][a-zA-Z0-9.\-]*\.[a-zA-Z]{2,}$/;
  if (!email || !emailRe.test(email)) {
    input.style.borderColor = 'var(--red)';
    input.placeholder = 'Please enter a valid email';
    setTimeout(() => { input.style.borderColor = ''; input.placeholder = 'Enter your email address'; }, 2000);
    return;
  }
  btn.textContent = '✅ Subscribed!';
  btn.style.background = 'linear-gradient(135deg,#34d399,#059669)';
  btn.disabled = true;
  input.value = '';
  setTimeout(() => {
    btn.textContent = 'Subscribe';
    btn.style.background = '';
    btn.disabled = false;
  }, 3000);
}

function renderFAQ() {
  const list = document.getElementById('faqList');
  if (!list) return;

  list.innerHTML = FAQ_DATA.map((item, i) => `
    <div class="faq-item" id="faq-${i}">
      <div class="faq-question" onclick="toggleFAQ(${i})">
        <span class="faq-q-text">${item.q}</span>
        <div class="faq-arrow">▼</div>
      </div>
      <div class="faq-answer">
        <div class="faq-answer-inner">${item.a}</div>
      </div>
    </div>
  `).join('');
}

function toggleFAQ(index) {
  const item = document.getElementById('faq-' + index);
  const wasOpen = item.classList.contains('open');

  document.querySelectorAll('.faq-item').forEach(el => el.classList.remove('open'));

  if (!wasOpen) item.classList.add('open');
}
renderFAQ();

// ══════════════════════════════════════════════════════════
//  SESSION RESTORE — runs on every page load
//  When user returns from /settings or /downloads, restore their session
// ══════════════════════════════════════════════════════════
(async function restoreSession() {
  const token = localStorage.getItem('vdl_token');
  if (!token) return; // not logged in

  const cachedUser = localStorage.getItem('vdl_user');
  if (cachedUser) {
    try {
      // Restore from cache immediately so UI shows instantly
      const user = JSON.parse(cachedUser);
      setLoggedInUI(user);
    } catch(e) {}
  }

  // Then verify token is still valid by calling /me
  try {
    const res = await fetch(`${API}/auth/me`, {
      headers: { Authorization: 'Bearer ' + token }
    });
    if (res.ok) {
      const userData = await res.json();
      // Update with fresh data from server (catches username changes)
      localStorage.setItem('vdl_user', JSON.stringify(userData));
      setLoggedInUI(userData);
    } else {
      // Token expired or invalid — sign out cleanly
      localStorage.removeItem('vdl_token');
      localStorage.removeItem('vdl_user');
      document.getElementById('authButtons').style.display = '';
      document.getElementById('userMenuWrap').style.display = 'none';
    }
  } catch(e) {
    // Network error — keep cached session, don't sign out
    console.warn('Session verify failed, using cached data');
  }
})();
