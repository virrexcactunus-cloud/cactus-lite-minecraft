"""Thin HTTP helpers shared by the catalog, auth and download code."""

import json
import time
import urllib.error
import urllib.parse
import urllib.request

from cactus_lite.core.paths import USER_AGENT

TIMEOUT = 30
CHUNK = 65536


class HttpError(RuntimeError):
    def __init__(self, status, body, message=None):
        super().__init__(message or f"HTTP {status}")
        self.status = status
        self.body = body


def _request(url, data=None, headers=None, method=None):
    hdrs = {"User-Agent": USER_AGENT, "Accept": "*/*"}
    if headers:
        hdrs.update(headers)
    return urllib.request.Request(url, data=data, headers=hdrs, method=method)


def get_bytes(url, timeout=TIMEOUT):
    with urllib.request.urlopen(_request(url), timeout=timeout) as r:
        return r.read()


def get_json(url, timeout=TIMEOUT):
    return json.loads(get_bytes(url, timeout=timeout).decode("utf-8"))


def post_json(url, payload, timeout=TIMEOUT):
    """POST JSON and return (status, parsed_body). Never raises on 4xx."""
    body = json.dumps(payload).encode("utf-8")
    req = _request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw.strip() else {})
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            parsed = json.loads(raw) if raw.strip() else {}
        except Exception:
            parsed = {"errorMessage": raw.decode("utf-8", "replace")[:300]}
        return e.code, parsed


def download(url, dst, total=None, on_progress=None, interval=0.15):
    """Stream a URL to dst. on_progress(done, total) is throttled to `interval`."""
    with urllib.request.urlopen(_request(url), timeout=TIMEOUT) as r:
        total = total or int(r.headers.get("Content-Length") or 0) or None
        done = 0
        last = 0.0
        with open(dst, "wb") as f:
            while True:
                chunk = r.read(CHUNK)
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
                now = time.time()
                if on_progress and now - last >= interval:
                    last = now
                    on_progress(done, total)
    if on_progress:
        on_progress(done, total)
    return done


def quote(value):
    return urllib.parse.quote(value or "")
