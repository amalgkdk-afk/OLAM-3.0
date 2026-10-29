# Setup for iteration-9 UI test: br-3 coordinator (password changed) + 1 extra br-3 pending TEST registration
import os
import uuid
import requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
API = os.environ["EXPO_PUBLIC_BACKEND_URL"].rstrip("/") + "/api"
h = {"Authorization": "Bearer " + requests.post(f"{API}/auth/login", json={"email": "qa-admin@olam.delta", "password": "QaAdmin#2026x"}, timeout=30).json()["access_token"]}
email = f"test_uicoord_{uuid.uuid4().hex[:6]}@olam.delta"
r = requests.post(f"{API}/staff", headers=h, json={"email": email, "password": "TempStart#2026", "name": "TEST UI Coord", "role": "coordinator", "branch_id": "br-3"}, timeout=30)
assert r.status_code == 200, r.text
t = requests.post(f"{API}/auth/login", json={"email": email, "password": "TempStart#2026"}, timeout=30).json()["access_token"]
r = requests.post(f"{API}/auth/change-password", headers={"Authorization": "Bearer " + t}, json={"current_password": "TempStart#2026", "new_password": "UiCoord#2026x"}, timeout=30)
assert r.status_code == 200, r.text
tag = uuid.uuid4().hex[:6]
r = requests.post(f"{API}/registrations", json={"full_name": f"TEST UI Bulk {tag}", "mobile": "98" + str(uuid.uuid4().int)[:8], "email": f"delivered+ui{tag}@resend.dev",
                  "branch_id": "br-3", "batch": "A2", "batch_no": "3", "faculty_name": "TEST Fac", "confirm": True, "privacy_accepted": True}, timeout=30)
assert r.status_code == 200, r.text
print("COORD", email, "UiCoord#2026x")
