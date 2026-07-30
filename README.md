# AcherLab Stress Tool - Controller + Worker

Kiến trúc 2 máy: **Server (Railway)** + **Worker (VPS)**

## Server (Railway)

```bash
cd server
pip install -r requirements.txt
export SECRET_KEY="your-secret-key"
python app.py
```

Deploy lên Railway:
1. Push `server/` lên GitHub
2. Import vào Railway
3. Set env: `SECRET_KEY`, `PORT` (Railway tự set)

## Worker (VPS)

```bash
cd worker
pip install -r requirements.txt
export SERVER_URL="https://your-app.railway.app"
export WORKER_TOKEN="<token từ server/data/worker.json>"
export MHDDOS_DIR="/path/to/MHDDoS"
python agent.py
```

## Luồng hoạt động

1. Browser gửi lệnh Start → Server API
2. Server lưu command, Worker poll lấy được
3. Worker chạy MHDDoS, gửi stats + logs về Server
4. Server trả về UI real-time qua polling
