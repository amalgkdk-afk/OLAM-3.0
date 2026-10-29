# Helper: set can_export for TEST UI coordinator (used by UI tests). Usage: python set_ui_coord_export.py true|false
import os
import sys
import requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
A = os.environ["EXPO_PUBLIC_BACKEND_URL"] + "/api"
t = requests.post(A + "/auth/login", json={"email": "amalgkrishnaadmin@olam.delta", "password": "Admin@12345"}).json()["access_token"]
r = requests.patch(A + "/staff/u-321bdac96eb3", headers={"Authorization": "Bearer " + t}, json={"can_export": sys.argv[1] == "true"})
print(r.status_code, r.json().get("can_export"))
