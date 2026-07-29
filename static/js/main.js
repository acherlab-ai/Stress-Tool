const statusDot = document.getElementById('statusDot');
const statusText = document.getElementById('statusText');
const startBtn = document.getElementById('startBtn');
const stopBtn = document.getElementById('stopBtn');
const logContainer = document.getElementById('logContainer');
const logCount = document.getElementById('logCount');

const statRequests = document.getElementById('statRequests');
const statSuccess = document.getElementById('statSuccess');
const statRate = document.getElementById('statRate');
const statUptime = document.getElementById('statUptime');
const progressBar = document.getElementById('progressBar');

const proxyHttp = document.getElementById('proxyHttp');
const proxyTotal = document.getElementById('proxyTotal');
const fetchProxyBtn = document.getElementById('fetchProxyBtn');

const cpuBar = document.getElementById('cpuBar');
const cpuValue = document.getElementById('cpuValue');
const memBar = document.getElementById('memBar');
const memValue = document.getElementById('memValue');
const cpuInfo = document.getElementById('cpuInfo');
const coreGrid = document.getElementById('coreGrid');

const methodSelect = document.getElementById('method');
const layerBtns = document.querySelectorAll('.layer-btn');

const rpcGroup = document.getElementById('rpcGroup');
const proxyTypeGroup = document.getElementById('proxyTypeGroup');

let lastLogIndex = 0;
let toastTimer = null;
let currentLayer = 7;

const cpuCanvas = document.getElementById('cpuChart');
const memCanvas = document.getElementById('memChart');
const cpuCtx = cpuCanvas.getContext('2d');
const memCtx = memCanvas.getContext('2d');

function showToast(message, type = 'success') {
  const toast = document.getElementById('toast');
  toast.textContent = message;
  toast.className = `toast ${type} show`;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove('show'), 3500);
}

function formatNumber(n) {
  return n.toLocaleString();
}

function setStatus(state) {
  statusDot.className = 'status-dot';
  if (state === 'running') {
    statusDot.classList.add('running');
    statusText.textContent = 'Running';
    statusText.style.color = 'var(--accent-green)';
  } else if (state === 'stopped') {
    statusDot.classList.add('stopped');
    statusText.textContent = 'Stopped';
    statusText.style.color = 'var(--accent-red)';
  } else {
    statusDot.classList.add('idle');
    statusText.textContent = 'Idle';
    statusText.style.color = 'var(--text-secondary)';
  }
}

function classifyLog(text) {
  if (/Attacking|Sent:/.test(text)) return 'status';
  if (/Finished|Completed|Done/.test(text)) return 'finished';
  if (/Proxy|proxy/.test(text)) return 'proxy';
  if (/Error|error|fail|Failed|Traceback/.test(text)) return 'error';
  if (/INFO/.test(text)) return 'info';
  return '';
}

function appendLogs(logs) {
  if (!logs.length) return;
  const empty = logContainer.querySelector('.log-empty');
  if (empty) empty.remove();
  const fragment = document.createDocumentFragment();
  logs.forEach(log => {
    const div = document.createElement('div');
    div.className = 'log-line';
    const timeSpan = document.createElement('span');
    timeSpan.className = 'log-time';
    timeSpan.textContent = log.time;
    const textSpan = document.createElement('span');
    textSpan.className = `log-text ${classifyLog(log.text)}`;
    textSpan.textContent = log.text;
    div.appendChild(timeSpan);
    div.appendChild(textSpan);
    fragment.appendChild(div);
  });
  logContainer.appendChild(fragment);
  logContainer.scrollTop = logContainer.scrollHeight;
  logCount.textContent = `${logContainer.children.length} lines`;
}

function drawSparkline(canvas, ctx, data, color) {
  const w = canvas.parentElement.clientWidth - 4;
  const h = canvas.height;
  canvas.width = w * devicePixelRatio;
  canvas.height = h * devicePixelRatio;
  ctx.scale(devicePixelRatio, devicePixelRatio);
  ctx.clearRect(0, 0, w, h);
  if (data.length < 2) {
    ctx.fillStyle = '#5a6485';
    ctx.font = '11px Inter';
    ctx.textAlign = 'center';
    ctx.fillText('Waiting...', w/2, h/2 + 4);
    return;
  }
  const pad = 2;
  const dw = (w - pad * 2) / Math.max(data.length - 1, 1);
  const values = data.map(d => d.value);
  const max = Math.max(...values, 10);
  const min = 0;
  const range = max - min || 1;
  ctx.beginPath();
  ctx.strokeStyle = color;
  ctx.lineWidth = 1.5;
  ctx.lineJoin = 'round';
  for (let i = 0; i < data.length; i++) {
    const x = pad + i * dw;
    const y = h - pad - ((data[i].value - min) / range) * (h - pad * 2);
    i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
  }
  ctx.stroke();
  const last = data[data.length - 1];
  ctx.fillStyle = color;
  ctx.beginPath();
  ctx.arc(pad + (data.length - 1) * dw, h - pad - ((last.value - min) / range) * (h - pad * 2), 2.5, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillStyle = color;
  ctx.font = '11px JetBrains Mono';
  ctx.textAlign = 'right';
  ctx.fillText(last.value.toFixed(1) + '%', w - pad, h - pad);
}

function updateCores(cores) {
  if (!cores || !cores.length) {
    coreGrid.innerHTML = '<div class="core-empty">No core data</div>';
    return;
  }
  coreGrid.innerHTML = '';
  cores.forEach(c => {
    const el = document.createElement('div');
    el.className = 'core-item';
    const usage = c.usage || 0;
    const color = usage > 80 ? 'var(--accent-red)' : usage > 50 ? 'var(--accent-yellow)' : 'var(--accent-cyan)';
    el.innerHTML = `
      <div class="core-label">Core ${c.core}</div>
      <div class="core-bar-bg">
        <div class="core-bar" style="width:${usage}%;background:${color}"></div>
      </div>
      <div class="core-value">${usage.toFixed(1)}%</div>
    `;
    coreGrid.appendChild(el);
  });
}

function toggleLayer(layer) {
  currentLayer = layer;
  layerBtns.forEach(b => b.classList.toggle('active', parseInt(b.dataset.layer) === layer));
  const opts = methodSelect.querySelectorAll('option');
  opts.forEach(o => {
    const inL7 = o.parentElement?.label === 'Layer7';
    const inL4 = o.parentElement?.label === 'Layer4';
    if (layer === 7) {
      o.style.display = inL7 ? '' : 'none';
    } else {
      o.style.display = inL4 ? '' : 'none';
    }
  });
  const l7vis = layer === 7 ? '' : 'none';
  rpcGroup.style.display = l7vis;
  proxyTypeGroup.style.display = l7vis;
  const urlInput = document.getElementById('url');
  urlInput.placeholder = layer === 7 ? 'https://example.com' : '1.2.3.4:80';
  if (layer === 4) {
    methodSelect.querySelector('optgroup[label="Layer4"] option')?.click();
  } else {
    methodSelect.querySelector('optgroup[label="Layer7"] option')?.click();
  }
}

async function pollSystem() {
  try {
    const res = await fetch('/api/system');
    const data = await res.json();
    const s = data.stats;
    if (s.running) {
      setStatus('running');
      statRequests.textContent = formatNumber(s.requests);
      statSuccess.textContent = formatNumber(s.success);
      statRate.textContent = s.rate + '%';
      statUptime.textContent = data.uptime;
      progressBar.style.width = Math.min(s.rate, 100) + '%';
      startBtn.disabled = true;
      stopBtn.disabled = false;
    } else if (s.requests > 0) {
      setStatus('stopped');
      statUptime.textContent = data.uptime;
      progressBar.style.width = Math.min(s.rate, 100) + '%';
      startBtn.disabled = false;
      stopBtn.disabled = true;
    } else {
      setStatus('idle');
      progressBar.style.width = '0%';
    }
    proxyHttp.textContent = data.proxies.http;
    proxyTotal.textContent = data.proxies.total;
    const sys = data.system;
    const cpu = parseFloat(sys.cpu) || 0;
    const mem = parseFloat(sys.memory) || 0;
    cpuBar.style.width = Math.min(cpu, 100) + '%';
    cpuValue.textContent = cpu.toFixed(1) + '%';
    memBar.style.width = Math.min(mem, 100) + '%';
    memValue.textContent = mem.toFixed(1) + '%';
    if (sys.cpu_info) {
      const ci = sys.cpu_info;
      cpuInfo.innerHTML = `<span class="cpu-model">${ci.model}</span> <span class="cpu-detail">${ci.cores} cores / ${ci.threads} threads</span>`;
    }
    updateCores(sys.cpu_per_core);
    drawSparkline(cpuCanvas, cpuCtx, sys.cpu_history || [], '#19D7FF');
    drawSparkline(memCanvas, memCtx, sys.mem_history || [], '#7B2FF7');
  } catch (e) {}
}

async function pollLogs() {
  try {
    const res = await fetch(`/api/logs?since=${lastLogIndex}`);
    const logs = await res.json();
    if (logs.length) {
      appendLogs(logs);
      lastLogIndex += logs.length;
    }
  } catch (e) {}
}

layerBtns.forEach(btn => {
  btn.addEventListener('click', () => toggleLayer(parseInt(btn.dataset.layer)));
});

document.getElementById('configForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  if (startBtn.disabled) return;
  const target = document.getElementById('url').value.trim();
  if (!target) {
    showToast('Please enter a target URL/IP', 'error');
    return;
  }
  startBtn.disabled = true;
  startBtn.textContent = 'Starting...';
  try {
    const payload = {
      method: document.getElementById('method').value,
      url: target,
      threads: parseInt(document.getElementById('threads').value) || 100,
      duration: parseInt(document.getElementById('duration').value) || 60,
      proxy_type: currentLayer === 7 ? parseInt(document.getElementById('proxyType').value) : 0,
      rpc: currentLayer === 7 ? parseInt(document.getElementById('rpc').value) || 10 : 1,
    };
    const res = await fetch('/api/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const result = await res.json();
    if (res.ok) {
      showToast('Attack started! Method: ' + payload.method);
      setStatus('running');
      stopBtn.disabled = false;
      lastLogIndex = 0;
      logContainer.innerHTML = '<div class="log-empty">Waiting for output...</div>';
      logCount.textContent = '0 lines';
    } else {
      showToast(result.error || 'Failed to start', 'error');
      startBtn.disabled = false;
    }
  } catch (e) {
    showToast('Connection error', 'error');
    startBtn.disabled = false;
  }
  startBtn.textContent = 'Start Attack';
});

stopBtn.addEventListener('click', async () => {
  stopBtn.disabled = true;
  try {
    const res = await fetch('/api/stop', { method: 'POST' });
    const result = await res.json();
    showToast(result.message || 'Attack stopped');
    setStatus('stopped');
    startBtn.disabled = false;
  } catch (e) {
    showToast('Failed to stop', 'error');
    stopBtn.disabled = false;
  }
});

fetchProxyBtn.addEventListener('click', async () => {
  fetchProxyBtn.disabled = true;
  fetchProxyBtn.innerHTML = '<span style="font-size:12px">Fetching...</span>';
  try {
    await fetch('/api/proxies/fetch', { method: 'POST' });
    showToast('Fetching proxies in background...');
    setTimeout(() => {
      fetchProxyBtn.disabled = false;
      fetchProxyBtn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg> Fetch';
    }, 3000);
  } catch (e) {
    showToast('Failed', 'error');
    fetchProxyBtn.disabled = false;
    fetchProxyBtn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg> Fetch';
  }
});

document.getElementById('logoutBtn').addEventListener('click', async () => {
  await fetch('/api/logout', { method: 'POST' });
  window.location.href = '/login';
});

toggleLayer(7);
setInterval(pollSystem, 1000);
setInterval(pollLogs, 1500);
pollSystem();
pollLogs();
