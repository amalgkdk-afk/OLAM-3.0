# OLAM 3.0 security-fix regression tests (SEC-001 forced pw change/lockout, SEC-002 CSV injection, SEC-003 hashed pass tokens, scanner)
import os
import csv
import io
import uuid
import concurrent.futures as cf
import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
OWNER = {"email": "amalgkrishnaadmin@olam.delta", "password": "Admin@12345"}
QA = {"email": "qa-admin@olam.delta", "password": "QaAdmin#2026x"}
EMAIL = "delivered@resend.dev"
CREATED = {"regs": [], "users": []}


def _login_raw(email, pw):
    return requests.post(f"{API}/auth/login", json={"email": email, "password": pw}, timeout=30)


def _hdr(r):
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="session")
def qa():
    r = _login_raw(QA["email"], QA["password"])
    assert r.status_code == 200, r.text
    assert r.json()["user"]["must_change_password"] is False
    return {"h": _hdr(r), "user": r.json()["user"]}


def _register(name="TEST Sec Student"):
    r = requests.post(f"{API}/registrations", json={
        "full_name": name, "mobile": "9" + str(uuid.uuid4().int)[:9],
        "email": EMAIL, "branch_id": "br-1", "batch": "TEST_Batch", "batch_no": "B12", "faculty_name": "TEST Faculty", "confirm": True}, timeout=30)
    assert r.status_code == 200, r.text
    CREATED["regs"].append(r.json()["id"])
    return r.json()


def _lookup(ref):
    return requests.post(f"{API}/registrations/lookup", json={"reference": ref, "email": EMAIL}, timeout=30)


def _scan(h, token):
    r = requests.post(f"{API}/scan", json={"token": token, "station": "TEST_station"}, headers=h, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


def _mk_staff(qa, role="scanner", pw="TestStart#123", branch=None):
    email = f"test_{role}_{uuid.uuid4().hex[:6]}@olam.delta"
    r = requests.post(f"{API}/staff", headers=qa["h"], json={
        "email": email, "password": pw, "name": f"TEST {role}", "role": role, "branch_id": branch}, timeout=30)
    assert r.status_code == 200, r.text
    assert r.json()["must_change_password"] is True
    CREATED["users"].append(r.json()["id"])
    return email, pw


# --- SEC-001 owner forced change ---
class TestOwnerForcedChange:
    def test_owner_login_must_change(self):
        r = _login_raw(OWNER["email"], OWNER["password"])
        assert r.status_code == 200, r.text
        assert r.json()["user"]["must_change_password"] is True
        h = _hdr(r)
        s = requests.get(f"{API}/stats", headers=h, timeout=30)
        assert s.status_code == 403 and "Password change required" in s.text
        m = requests.get(f"{API}/auth/me", headers=h, timeout=30)
        assert m.status_code == 200 and m.json()["email"] == OWNER["email"]


# --- SEC-001 lockout ---
class TestLockout:
    def test_lockout_after_5_failures(self, qa):
        email, pw = _mk_staff(qa)
        codes = [_login_raw(email, "WrongPass#999").status_code for _ in range(5)]
        assert codes == [401] * 5, codes
        r = _login_raw(email, pw)
        assert r.status_code == 429, r.text
        assert "too many failed sign-ins" in r.text.lower()


# --- new staff change password flow ---
class TestChangePassword:
    def test_change_password_flow(self, qa):
        email, pw = _mk_staff(qa, role="scanner")
        r = _login_raw(email, pw)
        assert r.status_code == 200 and r.json()["user"]["must_change_password"] is True
        h = _hdr(r)
        assert requests.get(f"{API}/scan/history", headers=h, timeout=30).status_code == 403
        bad = requests.post(f"{API}/auth/change-password", headers=h, json={"current_password": "nope-wrong-1", "new_password": "GoodPass12345"}, timeout=30)
        assert bad.status_code == 400 and "incorrect" in bad.text.lower()
        weak1 = requests.post(f"{API}/auth/change-password", headers=h, json={"current_password": pw, "new_password": "short1"}, timeout=30)
        assert weak1.status_code in (400, 422), weak1.text
        weak2 = requests.post(f"{API}/auth/change-password", headers=h, json={"current_password": pw, "new_password": "NoDigitsHereAtAll"}, timeout=30)
        assert weak2.status_code == 400, weak2.text
        ok = requests.post(f"{API}/auth/change-password", headers=h, json={"current_password": pw, "new_password": "BrandNewPass2026"}, timeout=30)
        assert ok.status_code == 200, ok.text
        me = requests.get(f"{API}/auth/me", headers=h, timeout=30).json()
        assert me["must_change_password"] is False
        assert requests.get(f"{API}/scan/history", headers=h, timeout=30).status_code == 200
        r2 = _login_raw(email, "BrandNewPass2026")
        assert r2.status_code == 200 and r2.json()["user"]["must_change_password"] is False


# --- last admin guard ---
class TestLastAdminGuard:
    def test_self_demote_blocked(self, qa):
        uid = qa["user"]["id"]
        r = requests.patch(f"{API}/staff/{uid}", headers=qa["h"], json={"role": "coordinator", "branch_id": "br-1"}, timeout=30)
        assert r.status_code == 400, r.text

    def test_self_deactivate_blocked(self, qa):
        uid = qa["user"]["id"]
        r = requests.patch(f"{API}/staff/{uid}", headers=qa["h"], json={"active": False}, timeout=30)
        assert r.status_code == 400, r.text
        me = requests.get(f"{API}/auth/me", headers=qa["h"], timeout=30).json()
        assert me["role"] == "super_admin" and me["active"] is True


# --- SEC-002 CSV injection ---
class TestCsvInjection:
    def test_csv_formula_neutralised(self, qa):
        reg = _register('=HYPERLINK("x")')
        reg2 = _register("+SUM(1)")
        r = requests.get(f"{API}/export/registrations.csv", headers=qa["h"], timeout=60)
        assert r.status_code == 200
        raw = r.text
        assert '"\'=HYPERLINK(""x"")"' in raw, "formula cell not prefixed/quoted"
        assert '"\'+SUM(1)"' in raw
        rows = list(csv.reader(io.StringIO(raw)))
        names = {row[0]: row[1] for row in rows[1:]}
        assert names[reg["reference"]] == "'=HYPERLINK(\"x\")"
        assert names[reg2["reference"]] == "'+SUM(1)"
        # all fields quoted
        for line in raw.strip().splitlines()[:5]:
            assert line.startswith('"') and line.rstrip("\r").endswith('"')


# --- SEC-003 hashed pass tokens + scanner ---
class TestPassTokens:
    def test_token_lifecycle_and_scan(self, qa):
        h = qa["h"]
        reg = _register()
        rid, ref = reg["id"], reg["reference"]
        assert requests.post(f"{API}/registrations/{rid}/approve", headers=h, timeout=30).status_code == 200
        lk = _lookup(ref).json()
        t1 = lk["pass_token"]
        assert t1 and lk["registration"]["status"] == "approved"
        assert "plain_token" not in str(lk)
        v = requests.post(f"{API}/pass/verify", json={"token": t1}, timeout=30)
        assert v.status_code == 200 and v.json()["registration"]["reference"] == ref
        old = requests.get(f"{API}/pass/verify/{t1}", timeout=30)
        assert old.status_code in (404, 405), old.status_code
        # idempotent approve
        assert requests.post(f"{API}/registrations/{rid}/approve", headers=h, timeout=30).status_code == 200
        assert _lookup(ref).json()["pass_token"] == t1
        # reject -> reapprove -> new token
        rj = requests.post(f"{API}/registrations/{rid}/reject", headers=h, json={"reason": "TEST reason"}, timeout=30)
        assert rj.status_code == 200, rj.text
        assert requests.post(f"{API}/pass/verify", json={"token": t1}, timeout=30).status_code == 404
        assert requests.post(f"{API}/registrations/{rid}/approve", headers=h, timeout=30).status_code == 200
        t2 = _lookup(ref).json()["pass_token"]
        assert t2 and t2 != t1
        old_scan = _scan(h, t1)
        assert old_scan["result"] in ("INVALID", "REVOKED"), old_scan
        assert _scan(h, t2)["result"] == "VALID"
        assert _scan(h, t2)["result"] == "ALREADY_CHECKED_IN"

    def test_concurrent_scans_single_valid(self, qa):
        h = qa["h"]
        reg = _register()
        assert requests.post(f"{API}/registrations/{reg['id']}/approve", headers=h, timeout=30).status_code == 200
        tok = _lookup(reg["reference"]).json()["pass_token"]
        with cf.ThreadPoolExecutor(max_workers=6) as ex:
            results = list(ex.map(lambda _: _scan(h, tok)["result"], range(6)))
        assert results.count("VALID") == 1, results
        assert results.count("ALREADY_CHECKED_IN") == 5, results


def test_zz_db_has_no_plain_token():
    """DB-level check: passes collection must not store plain_token."""
    from pymongo import MongoClient
    load_dotenv("/app/backend/.env")
    db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    assert db.passes.count_documents({"plain_token": {"$exists": True}}) == 0
    assert db.passes.count_documents({"token_hash": {"$exists": False}}) == 0


@pytest.fixture(scope="session", autouse=True)
def _cleanup():
    yield
    from pymongo import MongoClient
    load_dotenv("/app/backend/.env")
    db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    ids = CREATED["regs"]
    db.registrations.delete_many({"id": {"$in": ids}})
    db.passes.delete_many({"registration_id": {"$in": ids}})
    db.attendance.delete_many({"registration_id": {"$in": ids}})
    db.scan_attempts.delete_many({"station": "TEST_station"})
    db.users.delete_many({"id": {"$in": CREATED["users"]}})
