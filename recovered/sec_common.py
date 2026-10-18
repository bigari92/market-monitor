import urllib.request, urllib.error, json, gzip, time, threading

UA = "quant-factor-research/1.0 (non-commercial academic backtest)"
_lock = threading.Lock()
_last = [0.0]
MIN_INTERVAL = 0.12          # ~8 req/s, under SEC's 10/s limit

def _throttle():
    with _lock:
        dt = time.time() - _last[0]
        if dt < MIN_INTERVAL:
            time.sleep(MIN_INTERVAL - dt)
        _last[0] = time.time()

def get_json(url, retries=3):
    for a in range(retries):
        _throttle()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "gzip"})
            with urllib.request.urlopen(req, timeout=90) as r:
                raw = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.decompress(raw)
                return json.loads(raw.decode())
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if a == retries - 1:
                raise
            time.sleep(1.5 * (a + 1))
        except Exception:
            if a == retries - 1:
                raise
            time.sleep(1.5 * (a + 1))
    return None
