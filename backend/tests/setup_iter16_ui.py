# OLAM 3.0 iteration 16 UI setup: approved-absent, approved-to-be-scanned, already-checked-in, pending regs
import json
import sys
import requests
sys.path.insert(0, "/app/backend/tests")
from test_olam_api import API, ADMIN, _login, _register  # noqa: E402

h = _login(ADMIN["email"], ADMIN["password"])
out = {}
for key, br in (("absent1", "br-1"), ("toscan", "br-1"), ("absent2", "br-2"), ("checked", "br-1")):
    reg = _register(branch=br, name=f"TEST Absent {key}")
    assert requests.post(f"{API}/registrations/{reg['id']}/approve", headers=h, timeout=60).status_code == 200
    out[key] = reg["reference"]
s = requests.post(f"{API}/scan", headers=h, json={"token": out["checked"], "station": "TEST"}, timeout=30).json()
assert s["result"] == "VALID", s
out["pending"] = _register(name="TEST Absent pending")["reference"]
print(json.dumps(out))
