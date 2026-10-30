# OLAM 3.0 iteration 18 UI setup: one approved registration for WhatsApp pass sharing test
import json
import sys
import requests
sys.path.insert(0, "/app/backend/tests")
from test_olam_api import API, ADMIN, _login, _register, _lookup  # noqa: E402

h = _login(ADMIN["email"], ADMIN["password"])
reg = _register(name="TEST WhatsApp Share")
assert requests.post(f"{API}/registrations/{reg['id']}/approve", headers=h, timeout=60).status_code == 200
lk = _lookup(reg["reference"]).json()
print(json.dumps({"ref": reg["reference"], "email": "delivered@resend.dev", "token": lk.get("pass_token"),
                  "branch": lk["registration"]["branch_name"], "name": lk["registration"]["full_name"]}))
