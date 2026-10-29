# Creates a TEST coordinator (must_change_password) + approved TEST registration for UI security tests
import os
import json
import uuid
import requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
API = os.environ.get("EXPO_PUBLIC_BACKEND_URL").rstrip("/") + "/api"
r = requests.post(f"{API}/auth/login", json={"email": "qa-admin@olam.delta", "password": "QaAdmin#2026x"}, timeout=30)
h = {"Authorization": f"Bearer {r.json()['access_token']}"}
email = f"test_uicoord_{uuid.uuid4().hex[:6]}@olam.delta"
s = requests.post(f"{API}/staff", headers=h, json={"email": email, "password": "TempStart#2026", "name": "TEST UI Coord", "role": "coordinator", "branch_id": "br-1"}, timeout=30)
reg = requests.post(f"{API}/registrations", json={"full_name": "TEST UI Pass", "mobile": "9" + str(uuid.uuid4().int)[:9], "email": "delivered@resend.dev", "branch_id": "br-1", "batch": "TEST_Batch", "batch_no": "B12", "faculty_name": "TEST Faculty", "confirm": True, "privacy_accepted": True}, timeout=30).json()
a = requests.post(f"{API}/registrations/{reg['id']}/approve", headers=h, timeout=30)
print(json.dumps({"coord_email": email, "coord_status": s.status_code, "ref": reg["reference"], "approve": a.status_code}))
