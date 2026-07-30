let state = { running: false, lastLogLines: 0 }
let cpuHistory = [], memHistory = []
let toastTimer = null

const $ = id => document.getElementById(id)
const $$ = sel => document.querySelectorAll(sel)

function showToast(msg, type='success') {
  const t = $('toast')
  t.textContent = msg
  t.className = `toast ${type} show`
  clearTimeout(toastTimer)
  toastTimer = setTimeout(() => t.classList.remove('show'), 3000)
}

function formatNum(n) { return Number(n).toLocaleString() }

function setStatus(running) {
  const dot = $('statusDot'), text = $('statusText')
  if (running) {
    dot.className = 'status-dot running'
    text.textContent = 'Running'
    text.style.color = 'var(--accent-green)'
  } else if (state.running) {
    dot.className = 'status-dot stopped'
    text.textContent = 'Stopped'
    text.style.color = 'var(--accent-red)'
  } else {
    dot.className = 'status-dot idle'
    text.textContent = 'Idle'
    text.style.color = 'var(--text-secondary)'
  }
}

function setWorker(online) {
  const dot = $('workerDot'), text = $('workerText'), footer = $('footerWorker')
  dot.className = `worker-dot ${online ? 'online' : ''}`
  text.textContent = online ? 'Worker Online' : 'Worker Offline'
  text.style.color = online ? 'var(--accent-green)' : 'var(--accent-red)'
  if (footer) footer.textContent = online ? 'Worker Connected' : 'Worker Offline'
}

function classifyLog(t) {
  if (/Attacking|Sent:|Running/.test(t)) return 'status'
  if (/Finished|Completed|Done|Stopped/.test(t)) return 'finished'
  if (/Proxy|proxy/.test(t)) return 'proxy'
  if (/Error|error|fail|Failed|Traceback/.test(t)) return 'error'
  if (/^\[.*\]/.test(t)) return 'info'
  return ''
}

function appendLogs(logs) {
  if (!logs.length) return
  const c = $('logContainer')
  const empty = c.querySelector('.log-empty')
  if (empty) empty.remove()
  const frag = document.createDocumentFragment()
  logs.forEach(l => {
    const d = document.createElement('div')
    d.className = 'log-line'
    d.innerHTML = `<span class="log-time">${l.time}</span><span class="log-text ${classifyLog(l.text)}">${l.text}</span>`
    frag.appendChild(d)
  })
  c.appendChild(frag)
  c.scrollTop = c.scrollHeight
  $('logCount').textContent = `${c.children.length} lines`
}

function drawChart(canvas, ctx, data, color) {
  const w = canvas.parentElement.clientWidth - 4
  const h = canvas.height
  canvas.width = w * devicePixelRatio
  canvas.height = h * devicePixelRatio
  ctx.scale(devicePixelRatio, devicePixelRatio)
  ctx.clearRect(0, 0, w, h)
  if (data.length < 2) {
    ctx.fillStyle = '#5a6485'
    ctx.font = '10px Inter'
    ctx.textAlign = 'center'
    ctx.fillText('Waiting...', w/2, h/2 + 3)
    return
  }
  const pad = 2
  const dw = (w - pad*2) / Math.max(data.length-1, 1)
  const vals = data.map(d => d.value)
  const max = Math.max(...vals, 10)
  ctx.beginPath()
  ctx.strokeStyle = color
  ctx.lineWidth = 1.5
  ctx.lineJoin = 'round'
  for (let i = 0; i < data.length; i++) {
    const x = pad + i * dw
    const y = h - pad - ((data[i].value - 0) / max) * (h - pad*2)
    i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y)
  }
  ctx.stroke()
  const last = data[data.length-1]
  ctx.fillStyle = color
  ctx.beginPath()
  ctx.arc(pad + (data.length-1) * dw, h - pad - ((last.value-0)/max)*(h-pad*2), 2, 0, Math.PI*2)
  ctx.fill()
  ctx.fillStyle = color
  ctx.font = '10px JetBrains Mono'
  ctx.textAlign = 'right'
  ctx.fillText(last.value.toFixed(1)+'%', w-pad, h-pad)
}

function toggleLayer(layer) {
  $$('.layer-btn').forEach(b => b.classList.toggle('active', parseInt(b.dataset.layer) === layer))
  $$('#method optgroup').forEach(g => g.style.display = (layer === 7 && g.label === 'Layer7') || (layer === 4 && g.label === 'Layer4') ? '' : 'none')
  $('rpcGroup').style.display = layer === 7 ? '' : 'none'
  $('proxyTypeGroup').style.display = layer === 7 ? '' : 'none'
  $('url').placeholder = layer === 7 ? 'https://example.com' : '1.2.3.4:80'
}

function loadTargets(targets) {
  const list = $('targetList'), count = $('targetCount')
  if (!targets.length) {
    list.innerHTML = '<div class="target-empty">No saved targets</div>'
    count.textContent = '0'
    return
  }
  count.textContent = targets.length
  list.innerHTML = targets.map(t => `
    <div class="target-item" data-url="${t.url}">
      <div style="flex:1;min-width:0">
        <div class="target-name">${t.name || t.url}</div>
        <div class="target-url">${t.url}</div>
      </div>
      <button class="target-del" data-id="${t.id}" title="Delete">&times;</button>
    </div>
  `).join('')
  list.querySelectorAll('.target-item').forEach(el => {
    el.addEventListener('click', e => {
      if (e.target.closest('.target-del')) return
      $('url').value = el.dataset.url
      list.querySelectorAll('.target-item').forEach(i => i.classList.remove('selected'))
      el.classList.add('selected')
    })
  })
  list.querySelectorAll('.target-del').forEach(btn => {
    btn.addEventListener('click', async e => {
      e.stopPropagation()
      if (!confirm('Delete target?')) return
      try {
        const r = await fetch(`/api/targets/${btn.dataset.id}`, {method: 'DELETE'})
        if (r.ok) {
          const data = await r.json()
          loadTargets(data.targets || [])
          showToast('Target deleted')
        }
      } catch(e) { showToast('Delete failed', 'error') }
    })
  })
}

async function saveCurrentTarget() {
  const url = $('url').value.trim()
  if (!url) return
  try {
    const r = await fetch('/api/targets', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({url, name: url})
    })
    if (r.ok) {
      const data = await r.json()
      loadTargets(data.targets)
    }
  } catch(e) {}
}

async function poll() {
  try {
    const r = await fetch('/api/system')
    const data = await r.json()
    const s = data.stats || {}
    const w = data.worker || {}

    setWorker(w.online)

    if (s.running) {
      state.running = true
      setStatus(true)
      $('statRequests').textContent = formatNum(s.requests || 0)
      $('statSuccess').textContent = formatNum(s.success || 0)
      $('statRate').textContent = formatNum(s.rate || 0) + '/s'
      $('statUptime').textContent = s.uptime || '00:00:00'
      $('startBtn').disabled = true
      $('stopBtn').disabled = false
    } else if (state.running && (s.requests || 0) > 0) {
      state.running = false
      setStatus(false)
      $('statUptime').textContent = s.uptime || '00:00:00'
      $('startBtn').disabled = false
      $('stopBtn').disabled = true
    } else {
      state.running = false
      setStatus(false)
      $('statUptime').textContent = '00:00:00'
      $('startBtn').disabled = false
      $('stopBtn').disabled = true
    }

    const cpu = parseFloat(s.cpu) || 0
    const mem = parseFloat(s.memory) || 0
    $('cpuBar').style.width = Math.min(cpu, 100) + '%'
    $('cpuValue').textContent = cpu.toFixed(1) + '%'
    $('memBar').style.width = Math.min(mem, 100) + '%'
    $('memValue').textContent = mem.toFixed(1) + '%'

    if (w.cpu_info) {
      const ci = w.cpu_info
      $('cpuInfo').innerHTML = `<span class="cpu-model">${ci.model}</span> <span class="cpu-detail">${ci.cores}c/${ci.threads}t</span>`
    }

    const now = new Date()
    cpuHistory.push({time: now.toLocaleTimeString(), value: cpu})
    memHistory.push({time: now.toLocaleTimeString(), value: mem})
    if (cpuHistory.length > 60) cpuHistory.shift()
    if (memHistory.length > 60) memHistory.shift()

    drawChart($('cpuChart'), $('cpuChart').getContext('2d'), cpuHistory, '#19D7FF')
    drawChart($('memChart'), $('memChart').getContext('2d'), memHistory, '#7B2FF7')

    if (data.logs && data.logs.length > state.lastLogLines) {
      const newLogs = data.logs.slice(state.lastLogLines)
      appendLogs(newLogs)
      state.lastLogLines = data.logs.length
    }
  } catch(e) {}
}

async function pollTargets() {
  try {
    const r = await fetch('/api/targets')
    const targets = await r.json()
    loadTargets(targets)
  } catch(e) {}
}

$$('.layer-btn').forEach(btn => {
  btn.addEventListener('click', () => toggleLayer(parseInt(btn.dataset.layer)))
})

$('configForm').addEventListener('submit', async e => {
  e.preventDefault()
  if ($('startBtn').disabled) return
  const url = $('url').value.trim()
  if (!url) { showToast('Enter target URL', 'error'); return }
  $('startBtn').disabled = true
  $('startBtn').innerHTML = 'Sending...'
  try {
    const r = await fetch('/api/attack/start', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        method: $('method').value,
        url,
        threads: parseInt($('threads').value) || 100,
        duration: parseInt($('duration').value) || 60,
        proxy_type: parseInt($('proxyType').value) || 0,
        rpc: parseInt($('rpc').value) || 10,
      })
    })
    const d = await r.json()
    if (r.ok) {
      showToast('Attack sent to worker: ' + ($('method').value))
      $('stopBtn').disabled = false
      saveCurrentTarget()
    } else {
      showToast(d.error || 'Failed', 'error')
      $('startBtn').disabled = false
    }
  } catch(e) { showToast('Connection error', 'error'); $('startBtn').disabled = false }
  $('startBtn').innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg> Start'
})

$('stopBtn').addEventListener('click', async () => {
  $('stopBtn').disabled = true
  try {
    const r = await fetch('/api/attack/stop', {method: 'POST'})
    const d = await r.json()
    showToast(d.message || 'Stop sent')
    setTimeout(() => { $('startBtn').disabled = false }, 1000)
  } catch(e) { showToast('Failed', 'error'); $('stopBtn').disabled = false }
})

$('clearLogBtn').addEventListener('click', () => {
  $('logContainer').innerHTML = '<div class="log-empty">Cleared</div>'
  $('logCount').textContent = '0 lines'
  state.lastLogLines = 0
})

$('logoutBtn').addEventListener('click', async () => {
  await fetch('/api/logout', {method: 'POST'})
  window.location.href = '/login'
})

toggleLayer(7)
pollTargets()
setInterval(poll, 1200)
setInterval(pollTargets, 10000)
poll()
