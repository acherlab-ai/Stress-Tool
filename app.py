import os, signal, json, time, threading, subprocess, platform
from datetime import datetime
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

attack_process = None
attack_start_time = None
stats_cache = {"requests": 0, "success": 0, "rate": 0, "running": False}
log_buffer = []

def get_proxy_stats():
    path = "proxy_list.json"
    if not os.path.exists(path):
        return {"socks5": 0, "http": 0, "https": 0, "total": 0}
    try:
        with open(path) as f:
            data = json.load(f)
        socks5 = len(data.get("socks5", []))
        http = len(data.get("http", []))
        https = len(data.get("https", []))
        return {"socks5": socks5, "http": http, "https": https, "total": socks5 + http + https}
    except:
        return {"socks5": 0, "http": 0, "https": 0, "total": 0}

def get_system_info():
    try:
        if platform.system() == "Linux":
            cpu = subprocess.run(
                "top -bn1 | grep 'Cpu(s)' | awk '{print 100 - $NF}'",
                shell=True, capture_output=True, text=True, timeout=3
            ).stdout.strip()
            mem = subprocess.run(
                "free -m | awk 'NR==2{printf \"%.1f\", $3*100/$2}'",
                shell=True, capture_output=True, text=True, timeout=3
            ).stdout.strip()
        else:
            cpu = mem = "N/A"
        return {"cpu": cpu or "N/A", "memory": mem or "N/A"}
    except:
        return {"cpu": "N/A", "memory": "N/A"}

def get_uptime():
    if not attack_start_time:
        return "00:00:00"
    elapsed = int(time.time() - attack_start_time)
    h, m, s = elapsed // 3600, (elapsed % 3600) // 60, elapsed % 60
    return f"{h:02d}:{m:02d}:{s:02d}"

def parse_output(line):
    global stats_cache, log_buffer
    log_buffer.append({"time": datetime.now().strftime("%H:%M:%S"), "text": line})
    if len(log_buffer) > 200:
        log_buffer = log_buffer[-200:]
    if "STATUS" in line:
        try:
            parts = line.split("|")
            req_part = parts[0].split(":")[1].strip()
            ok_part = parts[1].split(":")[1].strip()
            rate_part = parts[2].split(":")[1].strip().rstrip("%")
            stats_cache["requests"] = int(req_part)
            stats_cache["success"] = int(ok_part)
            stats_cache["rate"] = float(rate_part)
        except:
            pass
    if "Finished" in line:
        try:
            parts = line.split("|")
            total = parts[0].split(":")[1].strip()
            ok = parts[1].split(":")[1].strip()
            rate = parts[2].split(":")[1].strip().rstrip("%")
            stats_cache["requests"] = int(total)
            stats_cache["success"] = int(ok)
            stats_cache["rate"] = float(rate)
        except:
            pass
        stats_cache["running"] = False

def monitor_output(proc):
    global stats_cache
    for line in iter(proc.stdout.readline, ""):
        if not line:
            break
        line = line.rstrip()
        if line:
            parse_output(line)
    proc.wait()
    stats_cache["running"] = False

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/system")
def api_system():
    proxy = get_proxy_stats()
    system = get_system_info()
    uptime = get_uptime()
    return jsonify({
        "proxies": proxy,
        "system": system,
        "uptime": uptime,
        "stats": stats_cache
    })

@app.route("/api/logs")
def api_logs():
    since = request.args.get("since", 0, type=int)
    return jsonify(log_buffer[since:])

@app.route("/api/start", methods=["POST"])
def api_start():
    global attack_process, attack_start_time, stats_cache, log_buffer
    if attack_process and attack_process.poll() is None:
        return jsonify({"error": "Attack already running"}), 400
    data = request.json
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"error": "URL is required"}), 400
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    threads = data.get("threads", 500)
    duration = data.get("duration", 3600)
    proxy_mode = data.get("proxy_mode", "both")
    no_cf = data.get("no_cf", False)
    log_buffer = []
    stats_cache = {"requests": 0, "success": 0, "rate": 0, "running": True}
    attack_start_time = time.time()
    cmd = [
        "python3", "Attack.py",
        "--url", url,
        "--threads", str(threads),
        "--duration", str(duration),
        "--proxy-mode", proxy_mode
    ]
    if no_cf:
        cmd.append("--no-cf")
    attack_process = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, bufsize=1
    )
    threading.Thread(target=monitor_output, args=(attack_process,), daemon=True).start()
    return jsonify({"message": "Attack started", "pid": attack_process.pid})

@app.route("/api/stop", methods=["POST"])
def api_stop():
    global attack_process, stats_cache
    if attack_process and attack_process.poll() is None:
        os.killpg(os.getpgid(attack_process.pid), signal.SIGTERM)
        attack_process.terminate()
        try:
            attack_process.wait(timeout=5)
        except:
            attack_process.kill()
        stats_cache["running"] = False
        parse_output("[STATUS] Stopped by user")
        return jsonify({"message": "Attack stopped"})
    return jsonify({"message": "No attack running"}), 400

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
