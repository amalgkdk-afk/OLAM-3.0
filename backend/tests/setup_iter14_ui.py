# OLAM 3.0 iteration 14 UI setup: approved (not checked-in) registrations for scanner welcome-card test
import json
import sys
import requests
sys.path.insert(0, "/app/backend/tests")
from test_olam_api import API, ADMIN, _login, _register  # noqa: E402

h = _login(ADMIN["email"], ADMIN["password"])
out = []
for i in range(2):
    reg = _register(name=f"TEST Welcome Guest{i}")
    r = requests.post(f"{API}/registrations/{reg['id']}/approve", headers=h, timeout=60)
    assert r.status_code == 200, r.text
    out.append(reg["reference"])
pend = _register(name="TEST Pending Guest")
print(json.dumps({"approved": out, "pending": pend["reference"]}))
