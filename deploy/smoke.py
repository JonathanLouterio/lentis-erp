"""CI check for the built image behind a simulated HTTPS reverse proxy."""
import json
import re
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE = "http://127.0.0.1:18000"


def request(path, method="GET"):
    req = Request(BASE + path, method=method, headers={"X-Forwarded-Proto": "https"})
    try:
        with urlopen(req, timeout=10) as response:
            return response.status, response.headers, response.read()
    except HTTPError as response:
        return response.code, response.headers, response.read()


for attempt in range(45):
    try:
        status, _, data = request("/healthz/")
        if status == 200 and json.loads(data)["status"] == "ok":
            break
    except (URLError, TimeoutError, ConnectionError):
        pass
    time.sleep(1)
else:
    raise SystemExit("Cloud image failed its database health check.")

status, headers, html = request("/")
assert status == 200 and b'Lentis' in html
assert "no-store" in headers["Cache-Control"]
assets = re.findall(rb'(?:src|href)="(/static/app/[^\"]+)"', html)
assert len(assets) >= 2, "Frontend build did not use /static/app/."
for asset in assets:
    assert request(asset.decode())[0] == 200, asset
assert request("/api/me/")[0] == 403
assert request("/api/auth/logout/", "POST")[0] == 403
assert request("/api/unknown/")[0] == 404
status, headers, data = request("/api/auth/csrf/")
assert status == 200 and json.loads(data)["csrfToken"]
assert "secure" in headers["Set-Cookie"].lower()
print("PASS: built image, PostgreSQL, frontend assets, anonymous access and CSRF.")
