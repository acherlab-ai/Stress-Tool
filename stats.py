#!/usr/bin/env python3
"""
AcherLab Stress Tool - Stats Monitor
Dung cho nguoi dung chay o may host rieng (ko dung GitHub).
Hien thi thong ke real-time: proxy, request, success rate, system info.

Cach dung:
  python3 stats.py                    # Monitor mac dinh
  python3 stats.py --interval 2       # Update moi 2s
  python3 stats.py --log stats.log    # Ghi log ra file
  python3 stats.py --json             # Xuat JSON
"""

import os, sys, json, time, platform, argparse
from datetime import datetime

class StatsMonitor:
    def __init__(self, interval=3, log_file=None, json_mode=False):
        self.interval = interval
        self.log_file = log_file
        self.json_mode = json_mode
        self.start_time = time.time()
        self.proxy_file = "proxy_list.json"
        self.prev_total = 0
        self.prev_ok = 0

    def get_proxy_stats(self):
        if not os.path.exists(self.proxy_file):
            return {"socks5": 0, "http": 0, "https": 0, "total": 0}
        with open(self.proxy_file) as f:
            data = json.load(f)
        socks5 = len(data.get("socks5", []))
        http = len(data.get("http", []))
        https = len(data.get("https", []))
        return {"socks5": socks5, "http": http, "https": https, "total": socks5 + http + https}

    def get_system_info(self):
        cpu = os.popen("top -bn1 | grep 'Cpu(s)' | sed 's/.*, *\\([0-9.]*\\)%* id.*/\\1/' | awk '{print 100 - $1}'").read().strip()
        mem = os.popen("free -m | awk 'NR==2{printf \"%.1f\", $3*100/$2}'").read().strip()
        if not cpu: cpu = "N/A"
        if not mem: mem = "N/A"
        return {"cpu": cpu, "memory": mem}

    def clear_screen(self):
        os.system("cls" if os.name == "nt" else "clear")

    def get_uptime(self):
        elapsed = int(time.time() - self.start_time)
        h, m, s = elapsed // 3600, (elapsed % 3600) // 60, elapsed % 60
        return f"{h:02d}:{m:02d}:{s:02d}"

    def display(self):
        proxy = self.get_proxy_stats()
        system = self.get_system_info()
        uptime = self.get_uptime()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if self.json_mode:
            data = {
                "timestamp": now, "uptime": uptime,
                "proxies": proxy, "system": system
            }
            print(json.dumps(data, indent=2))
            if self.log_file:
                with open(self.log_file, "a") as f:
                    f.write(json.dumps(data) + "\n")
            return

        self.clear_screen()
        print("""
╔══════════════════════════════════════════╗
║       ACHERLAB STRESS MONITOR            ║
╠══════════════════════════════════════════╣
║  Thoi gian: {time:<29} ║
║  Uptime:    {uptime:<29} ║
╠══════════════════════════════════════════╣
║  PROXY STATS                             ║
║  SOCKS5:   {socks5:<6}                              ║
║  HTTP:     {http:<6}                              ║
║  HTTPS:    {https:<6}                              ║
║  Total:    {total:<6}                              ║
╠══════════════════════════════════════════╣
║  SYSTEM                                   ║
║  CPU:      {cpu:<6}%                           ║
║  Memory:   {mem:<6}%                           ║
╠══════════════════════════════════════════╣
║  Huong dan: Ctrl+C de thoat               ║
╚══════════════════════════════════════════╝
""".format(
            time=now, uptime=uptime,
            socks5=proxy["socks5"], http=proxy["http"],
            https=proxy["https"], total=proxy["total"],
            cpu=system["cpu"], mem=system["memory"]
        ))

        if self.log_file:
            with open(self.log_file, "a") as f:
                f.write(f"[{now}] CPU:{system['cpu']}% MEM:{system['memory']}% PROXY:{proxy['total']} UPTIME:{uptime}\n")

    def run(self):
        try:
            while True:
                self.display()
                time.sleep(self.interval)
        except KeyboardInterrupt:
            print("\nMonitor stopped.")

def main():
    parser = argparse.ArgumentParser(description="AcherLab Stats Monitor")
    parser.add_argument("--interval", type=int, default=3, help="Update interval (seconds)")
    parser.add_argument("--log", type=str, help="Log file path")
    parser.add_argument("--json", action="store_true", help="JSON output mode")
    args = parser.parse_args()

    monitor = StatsMonitor(interval=args.interval, log_file=args.log, json_mode=args.json)
    monitor.run()

if __name__ == "__main__":
    main()
