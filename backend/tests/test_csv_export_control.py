# OLAM 3.0 - Coordinator CSV export control (can_export flag) tests
import csv
import io
import os
import uuid
import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
ADMIN = {"email": "qa-admin@olam.delta", "password": "QaAdmin#2026x"}
PW = "TestPass@123"
CSV = f"{API}/export/registrations.csv"


def _login(email, pw):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw}, timeout=30)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="module")
def admin():
    return _login(ADMIN["email"], ADMIN["password"])


@pytest.fixture(scope="module")
def users(admin):
    sfx = uuid.uuid4().hex[:6]
    out = {}
    for role, br in (("coordinator", "br-1"), ("scanner", None)):
        email = f"test_csv_{role}_{sfx}@olam.delta"
        r = requests.post(f"{API}/staff", headers=admin, json={
            "email": email, "password": PW, "name": f"TEST csv {role}", "role": role, "branch_id": br}, timeout=30)
        assert r.status_code == 200, r.text
        h = _login(email, PW)  # new staff must change password before using other endpoints (SEC-001)
        c = requests.post(f"{API}/auth/change-password", headers=h, json={"current_password": PW, "new_password": "TestPassNew2026"}, timeout=30)
        assert c.status_code == 200, c.text
        out[role] = {"id": r.json()["id"], "created": r.json(), "h": _login(email, "TestPassNew2026")}
    yield out
    for u in out.values():  # deactivate (no DELETE endpoint); DB cleanup via cleanup_test_data.py
        requests.patch(f"{API}/staff/{u['id']}", headers=admin, json={"active": False}, timeout=30)


def _branch_name(admin, bid):
    for b in requests.get(f"{API}/branches", headers=admin, timeout=30).json():
        if b["id"] == bid:
            return b["name"]


class TestCsvControl:
    def test_default_false(self, users):
        assert users["coordinator"]["created"]["can_export"] is False

    def test_me_returns_can_export(self, users):
        r = requests.get(f"{API}/auth/me", headers=users["coordinator"]["h"], timeout=30)
        assert r.status_code == 200 and r.json()["can_export"] is False

    def test_coordinator_forbidden_by_default(self, users):
        r = requests.get(CSV, headers=users["coordinator"]["h"], timeout=30)
        assert r.status_code == 403, r.text

    def test_enable_then_scoped_export(self, admin, users):
        c = users["coordinator"]
        r = requests.patch(f"{API}/staff/{c['id']}", headers=admin, json={"can_export": True}, timeout=30)
        assert r.status_code == 200 and r.json()["can_export"] is True
        assert requests.get(f"{API}/auth/me", headers=c["h"], timeout=30).json()["can_export"] is True
        lst = [s for s in requests.get(f"{API}/staff", headers=admin, timeout=30).json() if s["id"] == c["id"]]
        assert lst[0]["can_export"] is True
        r = requests.get(CSV, headers=c["h"], timeout=30)
        assert r.status_code == 200, r.text
        rows = list(csv.reader(io.StringIO(r.text)))
        assert rows[0][0] == "Reference"
        br1 = _branch_name(admin, "br-1")
        bi = rows[0].index("Branch")
        branches = {row[bi] for row in rows[1:]}
        assert branches <= {br1}, branches

    def test_disable_again_forbidden(self, admin, users):
        c = users["coordinator"]
        r = requests.patch(f"{API}/staff/{c['id']}", headers=admin, json={"can_export": False}, timeout=30)
        assert r.status_code == 200 and r.json()["can_export"] is False
        assert requests.get(CSV, headers=c["h"], timeout=30).status_code == 403

    def test_super_admin_always(self, admin):
        r = requests.get(CSV, headers=admin, timeout=30)
        assert r.status_code == 200 and r.text.lstrip('"').startswith("Reference")

    def test_scanner_forbidden(self, admin, users):
        s = users["scanner"]
        assert requests.get(CSV, headers=s["h"], timeout=30).status_code == 403
        requests.patch(f"{API}/staff/{s['id']}", headers=admin, json={"can_export": True}, timeout=30)
        assert requests.get(CSV, headers=s["h"], timeout=30).status_code == 403

    def test_coordinator_cannot_patch_self(self, users):
        c = users["coordinator"]
        r = requests.patch(f"{API}/staff/{c['id']}", headers=c["h"], json={"can_export": True}, timeout=30)
        assert r.status_code == 403

    def test_no_auth_401(self):
        assert requests.get(CSV, timeout=30).status_code in (401, 403)
