# AcherLab Stress Tool - Web Console

Web interface for the AcherLab Stress Testing Tool. Run stress tests from your browser on your own server.

## Quick Start

```bash
pip install -r requirements.txt
python3 app.py
```

Open http://localhost:5000 in your browser.

## Features

- Web UI to configure and launch L7 stress attacks
- Real-time stats: requests, success rate, uptime
- Live console log output
- System resource monitoring (CPU, Memory)
- Proxy status display
- Cloudflare bypass support
- Start/Stop attack control

## Parameters

| Param | Default | Description |
|-------|---------|-------------|
| URL | required | Target URL |
| Threads | 500 | Number of threads |
| Duration | 3600 | Duration in seconds |
| Proxy Mode | both | tor/proxylist/both/none |
| CF Bypass | enabled | Disable Cloudflare bypass |

## API Endpoints

- `GET /` - Web interface
- `GET /api/system` - System & proxy stats
- `GET /api/logs?since=N` - Attack logs
- `POST /api/start` - Start attack
- `POST /api/stop` - Stop attack

## Disclaimer

For authorized security testing only. AcherLab không chịu trách nhiệm với việc sử dụng tool này.
