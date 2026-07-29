"""
AcherLab Proxy Collector - Thu thap proxy mien phi cho stress testing
Chi su dung cho muc dich kiem tra bao mat co authorization.
AcherLab khong chiu trach nhiem ve viec su dung trai phep.
"""

import requests, json

PROXY_SOURCES = [
    "https://api.proxyscrape.com/v2/?request=getproxies&protocol=socks5&timeout=10000&country=all",
    "https://api.proxyscrape.com/v2/?request=getproxies&protocol=http&timeout=5000&country=all",
    "https://www.proxy-list.download/api/v1/get?type=socks5",
    "https://www.proxy-list.download/api/v1/get?type=https",
    "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks5.txt",
    "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
    "https://raw.githubusercontent.com/hookzof/socks5_list/master/proxy.txt",
    "https://raw.githubusercontent.com/clarketm/proxy-list/master/proxy-list-raw.txt",
]

def fetch_all_proxies():
    proxies = {"socks5": set(), "http": set(), "https": set()}
    for url in PROXY_SOURCES:
        try:
            resp = requests.get(url, timeout=15)
            if resp.status_code == 200:
                for line in resp.text.strip().split('\n'):
                    line = line.strip()
                    if line and ':' in line:
                        if 'socks5' in url.lower():
                            proxies["socks5"].add(line)
                        elif 'https' in url.lower():
                            proxies["https"].add(line)
                        else:
                            proxies["http"].add(line)
        except:
            continue
    with open("proxy_list.json", "w") as f:
        json.dump({k: list(v) for k, v in proxies.items()}, f, indent=2)
    total = sum(len(v) for v in proxies.values())
    print(f"[PROXY] Da thu thap {total} proxy")

if __name__ == "__main__":
    fetch_all_proxies()
