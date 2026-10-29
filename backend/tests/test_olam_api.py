# OLAM 3.0 backend regression tests: auth, public, registrations, RBAC, scan, revoke, stats, export
import os
import uuid
import concurrent.futures as cf
import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
ADMIN = {"email": "amalgkrishnaadmin@olam.delta", "password": "Admin@12345"}
STAFF_PW = "TestPass@123"


def _login(email, pw):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw}, timeout=30)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _register(branch="br-1", code=None, email="delivered@resend.dev"):
    code = code or "TEST_" + uuid.uuid4().hex[:8]
    r = requests.post(f"{API}/registrations", json={
        "full_name": "TEST Student", "student_code": code, "mobile": "9876543210",
        "email": email, "branch_id": branch, "batch": "TEST_Batch", "confirm": True}, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


def _lookup(ref, email="delivered@resend.dev"):
    return requests.post(f"{API}/registrations/lookup", json={"reference": ref, "email": email}, timeout=30)


def _scan(h, token):
    r = requests.post(f"{API}/scan", json={"token": token}, headers=h, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture(scope="session")
def admin():
    return _login(ADMIN["email"], ADMIN["password"])


@pytest.fixture(scope="session")
def staff(admin):
    sfx = uuid.uuid4().hex[:6]
    out = {}
    for role, br in (("coordinator", "br-1"), ("scanner", None)):
        email = f"test_{role}_{sfx}@olam.delta"
        r = requests.post(f"{API}/staff", headers=admin, json={
            "email": email, "password": STAFF_PW, "name": f"TEST {role}", "role": role, "branch_id": br}, timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["role"] == role
        out[role] = _login(email, STAFF_PW)
    return out


# --- Auth
class TestAuth:
    def test_admin_login(self):
        r = requests.post(f"{API}/auth/login", json=ADMIN, timeout=30)
        assert r.status_code == 200
        assert r.json()["user"]["role"] == "super_admin"

    def test_wrong_password(self):
        r = requests.post(f"{API}/auth/login", json={"email": ADMIN["email"], "password": "Wrong@1234"}, timeout=30)
        assert r.status_code == 401


# --- Public
class TestPublic:
    def test_branches_batches(self):
        b = requests.get(f"{API}/public/branches", timeout=30).json()
        ids = {x["id"] for x in b}
        assert {"br-1", "br-2", "br-3"} <= ids
        bt = requests.get(f"{API}/public/batches", timeout=30)
        assert bt.status_code == 200 and isinstance(bt.json(), list) and len(bt.json()) > 0


# --- Registration
class TestRegistration:
    def test_submit_pending_and_duplicate(self):
        code = "TEST_" + uuid.uuid4().hex[:8]
        reg = _register(code=code)
        assert reg["status"] == "pending"
        assert reg["reference"].startswith("OLM-") and len(reg["reference"]) == 10
        r = requests.post(f"{API}/registrations", json={
            "full_name": "TEST Dup", "student_code": code.lower(), "mobile": "9876543210",
            "email": "delivered@resend.dev", "branch_id": "br-1", "batch": "TEST_Batch", "confirm": True}, timeout=30)
        assert r.status_code == 409

    def test_confirm_false(self):
        r = requests.post(f"{API}/registrations", json={
            "full_name": "TEST X", "student_code": "TEST_" + uuid.uuid4().hex[:6], "mobile": "9876543210",
            "email": "delivered@resend.dev", "branch_id": "br-1", "batch": "B", "confirm": False}, timeout=30)
        assert r.status_code == 422

    def test_lookup_flow(self, admin):
        reg = _register()
        r = _lookup(reg["reference"])
        assert r.status_code == 200 and r.json()["pass_token"] is None
        assert _lookup(reg["reference"], "wrong@resend.dev").status_code == 404
        a = requests.post(f"{API}/registrations/{reg['id']}/approve", headers=admin, timeout=60)
        assert a.status_code == 200 and a.json()["status"] == "approved"
        tok = _lookup(reg["reference"]).json()["pass_token"]
        assert tok
        v = requests.get(f"{API}/pass/verify/{tok}", timeout=30)
        assert v.status_code == 200 and v.json()["registration"]["reference"] == reg["reference"]
        assert requests.get(f"{API}/pass/verify/garbage-token-xyz", timeout=30).status_code == 404


# --- RBAC
class TestRBAC:
    def test_coordinator_scope(self, staff):
        reg2 = _register(branch="br-2")
        r = requests.post(f"{API}/registrations/{reg2['id']}/approve", headers=staff["coordinator"], timeout=30)
        assert r.status_code == 403
        lst = requests.get(f"{API}/registrations", headers=staff["coordinator"], timeout=30).json()
        assert len(lst) > 0 and all(x["branch_id"] == "br-1" for x in lst)

    def test_scanner_forbidden(self, staff):
        reg = _register()
        h = staff["scanner"]
        assert requests.post(f"{API}/registrations/{reg['id']}/approve", headers=h, timeout=30).status_code == 403
        assert requests.get(f"{API}/stats", headers=h, timeout=30).status_code == 403
        assert requests.get(f"{API}/export/registrations.csv", headers=h, timeout=30).status_code == 403


# --- Scan
class TestScan:
    def _approved_token(self, admin):
        reg = _register()
        requests.post(f"{API}/registrations/{reg['id']}/approve", headers=admin, timeout=60)
        return reg, _lookup(reg["reference"]).json()["pass_token"]

    def test_valid_then_duplicate(self, admin, staff):
        reg, tok = self._approved_token(admin)
        assert _scan(staff["scanner"], tok)["result"] == "VALID"
        assert _scan(staff["scanner"], tok)["result"] == "ALREADY_CHECKED_IN"

    def test_concurrent_scans(self, admin, staff):
        reg, tok = self._approved_token(admin)
        with cf.ThreadPoolExecutor(5) as ex:
            res = list(ex.map(lambda _: _scan(staff["scanner"], tok)["result"], range(5)))
        assert res.count("VALID") == 1, res
        assert res.count("ALREADY_CHECKED_IN") == 4, res
        hist = requests.get(f"{API}/scan/history", headers=admin, timeout=30).json()
        assert sum(1 for h in hist if h["reference"] == reg["reference"]) == 1

    def test_invalid_manual_pending(self, admin, staff):
        assert _scan(staff["scanner"], "garbage-token-123")["result"] == "INVALID"
        reg, _ = self._approved_token(admin)
        assert _scan(staff["scanner"], reg["reference"])["result"] == "VALID"
        pend = _register()
        assert _scan(staff["scanner"], pend["reference"])["result"] == "NOT_APPROVED"

    def test_reject_revokes_and_reapprove(self, admin, staff):
        reg, old = self._approved_token(admin)
        r = requests.post(f"{API}/registrations/{reg['id']}/reject", headers=admin, json={"reason": "TEST revoke"}, timeout=30)
        assert r.status_code == 200 and r.json()["status"] == "rejected"
        assert _scan(staff["scanner"], old)["result"] == "REVOKED"
        requests.post(f"{API}/registrations/{reg['id']}/approve", headers=admin, timeout=60)
        new = _lookup(reg["reference"]).json()["pass_token"]
        assert new and new != old
        assert _scan(staff["scanner"], old)["result"] != "VALID"
        assert _scan(staff["scanner"], new)["result"] == "VALID"


# --- Stats & Export
class TestStatsExport:
    def test_stats_match_list(self, admin):
        s = requests.get(f"{API}/stats", headers=admin, timeout=30)
        assert s.status_code == 200
        s = s.json()
        regs = requests.get(f"{API}/registrations", headers=admin, timeout=60).json()
        print("STATS", {k: v for k, v in s.items() if not isinstance(v, list)})
        assert s["total"] == len(regs)
        assert s.get("approved") == sum(1 for r in regs if r["status"] == "approved")
        assert s.get("pending") == sum(1 for r in regs if r["status"] == "pending")
        assert s.get("checked_in") == sum(1 for r in regs if r["checked_in"])

    def test_export_scoping(self, admin, staff):
        r = requests.get(f"{API}/export/registrations.csv", headers=admin, timeout=60)
        assert r.status_code == 200 and "text/csv" in r.headers.get("content-type", "")
        assert "br-2" in r.text or "Branch" in r.text
        # coordinators need admin-granted can_export since iteration 3
        assert requests.get(f"{API}/export/registrations.csv", headers=staff["coordinator"], timeout=60).status_code == 403
        me = requests.get(f"{API}/auth/me", headers=staff["coordinator"], timeout=30).json()
        assert requests.patch(f"{API}/staff/{me['id']}", headers=admin, json={"can_export": True}, timeout=30).status_code == 200
        c = requests.get(f"{API}/export/registrations.csv", headers=staff["coordinator"], timeout=60)
        assert c.status_code == 200
        lines = c.text.strip().splitlines()
        print("COORD CSV HEADER:", lines[0])
        admin_lines = r.text.strip().splitlines()
        assert 1 < len(lines) < len(admin_lines)


# --- Edge cases: staff validation, deactivation, reject validation, scanner PII access
class TestEdge:
    def test_duplicate_staff_email(self, admin):
        r = requests.post(f"{API}/staff", headers=admin, json={
            "email": ADMIN["email"], "password": STAFF_PW, "name": "dup", "role": "scanner"}, timeout=30)
        assert r.status_code == 409, r.status_code

    def test_coordinator_without_branch_rejected(self, admin):
        r = requests.post(f"{API}/staff", headers=admin, json={
            "email": f"test_nobranch_{uuid.uuid4().hex[:5]}@olam.delta", "password": STAFF_PW,
            "name": "TEST nobranch", "role": "coordinator"}, timeout=30)
        print("coordinator w/o branch ->", r.status_code)
        assert r.status_code in (400, 422)

    def test_coordinator_invalid_branch_rejected(self, admin):
        r = requests.post(f"{API}/staff", headers=admin, json={
            "email": f"test_badbranch_{uuid.uuid4().hex[:5]}@olam.delta", "password": STAFF_PW,
            "name": "TEST badbranch", "role": "coordinator", "branch_id": "br-doesnotexist"}, timeout=30)
        print("coordinator invalid branch ->", r.status_code)
        assert r.status_code in (400, 422)

    def test_deactivated_staff_token_invalid(self, admin):
        email = f"test_deact_{uuid.uuid4().hex[:5]}@olam.delta"
        u = requests.post(f"{API}/staff", headers=admin, json={
            "email": email, "password": STAFF_PW, "name": "TEST deact", "role": "scanner"}, timeout=30).json()
        h = _login(email, STAFF_PW)
        p = requests.patch(f"{API}/staff/{u['id']}", headers=admin, json={"active": False}, timeout=30)
        assert p.status_code == 200
        assert requests.post(f"{API}/scan", headers=h, json={"token": "garbage-1234"}, timeout=30).status_code == 401

    def test_reject_reason_validation(self, admin):
        reg = _register()
        r = requests.post(f"{API}/registrations/{reg['id']}/reject", headers=admin, json={"reason": "x"}, timeout=30)
        assert r.status_code == 422

    def test_approve_latency(self, admin):
        import time
        reg = _register()
        t = time.time()
        requests.post(f"{API}/registrations/{reg['id']}/approve", headers=admin, timeout=60)
        dt = time.time() - t
        print(f"approve latency {dt:.2f}s")
        assert dt < 5
