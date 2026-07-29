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

const proxySocks5 = document.getElementById('proxySocks5');
const proxyHttp = document.getElementById('proxyHttp');
const proxyHttps = document.getElementById('proxyHttps');
const proxyTotal = document.getElementById('proxyTotal');

const cpuBar = document.getElementById('cpuBar');
const cpuValue = document.getElementById('cpuValue');
const memBar = document.getElementById('memBar');
const memValue = document.getElementById('memValue');

let lastLogIndex = 0;
let toastTimer = null;

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
  if (/STATUS|Finished/.test(text)) return 'status';
  if (/Finished/.test(text)) return 'finished';
  if (/PROXY/.test(text)) return 'proxy';
  if (/Error|error|fail|Failed/.test(text)) return 'error';
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

  // parse stats from logs for live display
  const lastLog = logs[logs.length - 1];
  if (lastLog) {
    const m = lastLog.text.match(/\[STATUS\]\s*([\d,]+)\s*req\s*\|\s*OK:\s*([\d,]+)\s*\|\s*Rate:\s*([\d.]+)%/);
    if (m) {
      statRequests.textContent = formatNumber(parseInt(m[1].replace(/,/g, '')));
      statSuccess.textContent = formatNumber(parseInt(m[2].replace(/,/g, '')));
      statRate.textContent = m[3] + '%';
    }
    const m2 = lastLog.text.match(/Finished!\s*Total:\s*([\d,]+)\s*\|\s*OK:\s*([\d,]+)\s*\|\s*Rate:\s*([\d.]+)%/);
    if (m2) {
      statRequests.textContent = formatNumber(parseInt(m2[1].replace(/,/g, '')));
      statSuccess.textContent = formatNumber(parseInt(m2[2].replace(/,/g, '')));
      statRate.textContent = m2[3] + '%';
    }
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
      progressBar.style.width = '0%';
    }

    proxySocks5.textContent = data.proxies.socks5;
    proxyHttp.textContent = data.proxies.http;
    proxyHttps.textContent = data.proxies.https;
    proxyTotal.textContent = data.proxies.total;

    const cpu = parseFloat(data.system.cpu) || 0;
    const mem = parseFloat(data.system.memory) || 0;
    cpuBar.style.width = Math.min(cpu, 100) + '%';
    cpuValue.textContent = cpu.toFixed(1) + '%';
    memBar.style.width = Math.min(mem, 100) + '%';
    memValue.textContent = mem.toFixed(1) + '%';

  } catch (e) {
    // silent
  }
}

async function pollLogs() {
  try {
    const res = await fetch(`/api/logs?since=${lastLogIndex}`);
    const logs = await res.json();
    if (logs.length) {
      appendLogs(logs);
      lastLogIndex += logs.length;
    }
  } catch (e) {
    // silent
  }
}

document.getElementById('configForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  if (startBtn.disabled) return;

  const url = document.getElementById('url').value.trim();
  if (!url) {
    showToast('Please enter a target URL', 'error');
    return;
  }

  startBtn.disabled = true;
  startBtn.textContent = 'Starting...';

  try {
    const payload = {
      url,
      threads: parseInt(document.getElementById('threads').value) || 500,
      duration: parseInt(document.getElementById('duration').value) || 3600,
      proxy_mode: document.getElementById('proxyMode').value,
      no_cf: document.getElementById('noCf').checked,
    };

    const res = await fetch('/api/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const result = await res.json();
    if (res.ok) {
      showToast('Attack started successfully!');
      setStatus('running');
      stopBtn.disabled = false;
      lastLogIndex = 0;
      logContainer.innerHTML = '';
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

setInterval(pollSystem, 1000);
setInterval(pollLogs, 1500);
pollSystem();
pollLogs();
