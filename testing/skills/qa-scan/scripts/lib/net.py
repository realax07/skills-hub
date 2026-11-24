"""Сеть qa-scan: HTTP и XML-RPC клиент с записью и воспроизведением ответов (stdlib).

Запись (--record DIR) кладёт каждый ответ в DIR/<хеш>.json как {"key": …, "body": …} — без заголовков и токенов.
Воспроизведение (--replay DIR) отдаёт ответы из этих файлов без сети: так скилл проверяется без аккаунта в TMS.
Ключ — «МЕТОД путь?параметры [тело]», для XML-RPC — «xmlrpc метод параметры» без devKey.
"""
import base64
import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
import xmlrpc.client
from pathlib import Path


class HttpError(Exception):
    def __init__(self, status, key, text=""):
        super().__init__(f"HTTP {status}: {key} {text[:300]}")
        self.status = status
        self.key = key


class Client:
    def __init__(self, base, headers=None, replay=None, record=None, timeout=60, delay=0.0, retries=3):
        self.base = base.rstrip("/") if base else ""
        self.headers = dict(headers or {})
        self.timeout = timeout
        self.delay = delay
        self.retries = retries
        self.record = Path(record) if record else None
        self.replay = None
        self.calls = 0
        if replay:
            self.replay = {}
            rd = Path(replay)
            if not rd.is_dir():
                raise FileNotFoundError(f"нет папки ответов {replay}")
            for f in sorted(rd.glob("*.json")):
                try:
                    d = json.loads(f.read_text(encoding="utf-8"))
                except ValueError as e:
                    raise ValueError(f"{f}: не JSON ({e})")
                if isinstance(d, dict) and "key" in d:
                    self.replay[d["key"]] = d
        if self.record:
            self.record.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def basic(user, key):
        return "Basic " + base64.b64encode(f"{user}:{key}".encode()).decode()

    def _key(self, method, path, body=None):
        k = f"{method} {path}"
        if body is not None:
            k += " " + json.dumps(body, ensure_ascii=False, sort_keys=True)
        return k

    def _save(self, key, body):
        if self.record:
            name = hashlib.sha1(key.encode("utf-8")).hexdigest()[:16] + ".json"
            (self.record / name).write_text(json.dumps({"key": key, "body": body}, ensure_ascii=False, indent=1),
                                            encoding="utf-8")

    def _from_replay(self, key):
        if key not in self.replay:
            raise HttpError(404, key, "(нет в записанных ответах)")
        d = self.replay[key]
        if d.get("status", 200) >= 400:
            raise HttpError(d["status"], key, json.dumps(d.get("body"), ensure_ascii=False))
        return d.get("body")

    def request(self, method, path, body=None):
        """path — всё после base (с параметрами). Возвращает разобранный JSON."""
        key = self._key(method, path, body)
        self.calls += 1
        if self.replay is not None:
            return self._from_replay(key)
        url = path if path.startswith("http") else self.base + ("" if path.startswith(("/", "?")) else "/") + path
        data = json.dumps(body).encode() if body is not None else None
        hdr = {"Accept": "application/json", **self.headers}
        if data is not None:
            hdr["Content-Type"] = "application/json"
        last = None
        for attempt in range(self.retries + 1):
            if self.delay:
                time.sleep(self.delay)
            req = urllib.request.Request(url, data=data, headers=hdr, method=method)
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    raw = r.read().decode("utf-8", errors="replace")
                    res = json.loads(raw) if raw.strip() else None
                    self._save(key, res)
                    return res
            except urllib.error.HTTPError as e:
                text = e.read().decode("utf-8", errors="replace")
                last = HttpError(e.code, key, text)
                if e.code in (429, 500, 502, 503, 504) and attempt < self.retries:
                    wait = float(e.headers.get("Retry-After") or 2 ** (attempt + 1))
                    time.sleep(min(wait, 60))
                    continue
                raise last
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                last = HttpError(0, key, str(e))
                if attempt < self.retries:
                    time.sleep(2 ** (attempt + 1))
                    continue
                raise last
        raise last

    def get(self, path):
        return self.request("GET", path)

    def post(self, path, body):
        return self.request("POST", path, body)

    def download(self, path, dest):
        """Скачать файл. В режиме воспроизведения не скачивает (вернёт False)."""
        if self.replay is not None:
            return False
        url = path if path.startswith("http") else self.base + ("" if path.startswith(("/", "?")) else "/") + path
        req = urllib.request.Request(url, headers=self.headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                dest = Path(dest)
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(r.read())
                return True
        except (urllib.error.URLError, OSError):
            return False

    def xmlrpc(self, method, params, secret_keys=("devKey",)):
        shown = {k: v for k, v in params.items() if k not in secret_keys}
        key = f"xmlrpc {method} " + json.dumps(shown, ensure_ascii=False, sort_keys=True)
        self.calls += 1
        if self.replay is not None:
            return self._from_replay(key)
        proxy = xmlrpc.client.ServerProxy(self.base, allow_none=True)
        try:
            res = getattr(proxy, method)(params)
        except xmlrpc.client.Fault as e:
            raise HttpError(500, key, e.faultString)
        except (OSError, xmlrpc.client.ProtocolError) as e:
            raise HttpError(0, key, str(e))
        res = json.loads(json.dumps(res, default=str))
        self._save(key, res)
        return res


def qs(params):
    return urllib.parse.urlencode([(k, v) for k, v in params.items() if v is not None and v != ""])
