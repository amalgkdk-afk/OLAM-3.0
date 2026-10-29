# OLAM 3.0 iteration-8 UI setup: restore default settings + create a br-1 coordinator without CSV permission
import os
import uuid
import requests
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")
API = os.environ.get("EXPO_PUBLIC_BACKEND_URL").rstrip("/") + "/api"
MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]].settings.delete_many({})
h = {"Authorization": "Bearer " + requests.post(f"{API}/auth/login", json={"email": "qa-admin@olam.delta", "password": "QaAdmin#2026x"}, timeout=30).json()["access_token"]}
email = f"test_ui8_coord_{uuid.uuid4().hex[:5]}@olam.delta"
r = requests.post(f"{API}/staff", headers=h, json={"email": email, "password": "TestPass@123", "name": "TEST UI8 Coord", "role": "coordinator", "branch_id": "br-1"}, timeout=30)
t = requests.post(f"{API}/auth/login", json={"email": email, "password": "TestPass@123"}, timeout=30).json()["access_token"]
requests.post(f"{API}/auth/change-password", headers={"Authorization": f"Bearer {t}"}, json={"current_password": "TestPass@123", "new_password": "TestPassNew2026"}, timeout=30).raise_for_status()
print("COORD", email, r.json()["id"])
print("PUBLIC", requests.get(f"{API}/public/settings", timeout=30).json()["registration_open"])
