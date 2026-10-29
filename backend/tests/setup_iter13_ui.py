# iteration-13 UI setup: one approved TEST registration (resend.dev) for /my-pass -> /pass background check
import json, os, uuid, requests
from dotenv import load_dotenv
load_dotenv("/app/frontend/.env")
API = os.environ["EXPO_PUBLIC_BACKEND_URL"].rstrip("/") + "/api"
h = {"Authorization": "Bearer " + requests.post(f"{API}/auth/login", json={"email": "qa-admin@olam.delta", "password": "QaAdmin#2026x"}).json()["access_token"]}
tag = uuid.uuid4().hex[:6]
email = f"delivered+olam13ui{tag}@resend.dev"
r = requests.post(f"{API}/registrations", json={"full_name": f"TEST Iter13UI {tag}", "mobile": "9" + str(uuid.uuid4().int)[:9], "email": email,
    "branch_id": "br-1", "batch": "A1", "batch_no": "7", "faculty_name": "TEST Faculty", "confirm": True, "privacy_accepted": True}).json()
requests.post(f"{API}/registrations/{r['id']}/approve", headers=h)
out = {"id": r["id"], "ref": r["reference"], "email": email}
json.dump(out, open("/tmp/iter13_ui.json", "w")); print(json.dumps(out))
