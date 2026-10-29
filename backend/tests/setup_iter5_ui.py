# Iteration 5 UI setup: long-name TEST coordinator + TEST scanner (passwords already changed) + approved TEST registration with pass token
import os
import json
import uuid
import requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
API = os.environ.get("EXPO_PUBLIC_BACKEND_URL").rstrip("/") + "/api"
NEW = "UiReadyPass2026"
r = requests.post(f"{API}/auth/login", json={"email": "qa-admin@olam.delta", "password": "QaAdmin#2026x"}, timeout=30)
h = {"Authorization": f"Bearer {r.json()['access_token']}"}
out = {}
for role, br, name in (("coordinator", "br-1", "TEST Coordinator Bartholomew Maximilian Alexandrovich Longname"), ("scanner", None, "TEST UI Scanner")):
    email = f"test_ui5_{role}_{uuid.uuid4().hex[:5]}@olam.delta"
    requests.post(f"{API}/staff", headers=h, json={"email": email, "password": "TempStart#2026", "name": name, "role": role, "branch_id": br}, timeout=30)
    t = requests.post(f"{API}/auth/login", json={"email": email, "password": "TempStart#2026"}, timeout=30).json()["access_token"]
    c = requests.post(f"{API}/auth/change-password", headers={"Authorization": f"Bearer {t}"}, json={"current_password": "TempStart#2026", "new_password": NEW}, timeout=30)
    out[role] = {"email": email, "pw": NEW, "chpw": c.status_code}
reg = requests.post(f"{API}/registrations", json={"full_name": "TEST UI5 Pass", "mobile": "9" + str(uuid.uuid4().int)[:9], "email": "delivered@resend.dev", "branch_id": "br-1", "batch": "TEST_Batch", "batch_no": "B12", "faculty_name": "TEST Faculty", "confirm": True, "privacy_accepted": True}, timeout=30).json()
requests.post(f"{API}/registrations/{reg['id']}/approve", headers=h, timeout=30)
lk = requests.post(f"{API}/registrations/lookup", json={"reference": reg["reference"], "email": "delivered@resend.dev"}, timeout=30).json()
out["ref"] = reg["reference"]
out["token"] = lk.get("pass_token")
print(json.dumps(out))
