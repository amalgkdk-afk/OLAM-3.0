# OLAM 3.0 iteration 19 UI setup: two approved registrations (10-digit and +91 mobiles) for absent WhatsApp reminder test
import json
import sys
import uuid
import requests
sys.path.insert(0, "/app/backend/tests")
from test_olam_api import API, ADMIN, _login, _register  # noqa: E402

h = _login(ADMIN["email"], ADMIN["password"])
m1 = "98765" + str(uuid.uuid4().int)[:5]
m2 = "97654" + str(uuid.uuid4().int)[:5]
r1 = _register(name="TEST WA Ten", mobile=m1)
r2 = _register(name="TEST WA Plus", mobile="+91 " + m2[:5] + " " + m2[5:])
for r in (r1, r2):
    assert requests.post(f"{API}/registrations/{r['id']}/approve", headers=h, timeout=60).status_code == 200
print(json.dumps({"ten": {"ref": r1["reference"], "mobile": m1}, "plus": {"ref": r2["reference"], "mobile": m2}}))
