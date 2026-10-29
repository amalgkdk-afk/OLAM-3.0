# OLAM 3.0 iteration-10: email 429 retry (bulk approve -> all 'sent'), resend-email RBAC, reminders status/409/pending=0,
# login grammar, regression (role+branch sign-in, bulk skip reasons, scan VALID->ALREADY_CHECKED_IN).
# Restart backend before running (in-memory rate limits). Uses only @resend.dev emails. Slow (~3-6 min).
import os
import time
import uuid
import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
QA = {"email": "qa-admin@olam.delta", "password": "QaAdmin#2026x"}
PW = {"coordinator": "CoordNew#2026x", "scanner": "ScanNew#2026x"}


def _login(email, pw, **extra):
    return requests.post(f"{API}/auth/login", json={"email": email, "password": pw, **extra}, timeout=30)


def _h(tok):
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="module")
def admin_h():
    r = _login(QA["email"], QA["password"])
    assert r.status_code == 200, r.text
    return _h(r.json()["access_token"])


def _make_staff(admin_h, role, branch_id):
    email = f"test_{role}_{uuid.uuid4().hex[:6]}@olam.delta"
    body = {"email": email, "password": "TempStart#2026", "name": f"TEST {role}", "role": role}
    if branch_id:
        body["branch_id"] = branch_id
    r = requests.post(f"{API}/staff", headers=admin_h, json=body, timeout=30)
    assert r.status_code == 200, r.text
    tok = _login(email, "TempStart#2026").json()["access_token"]
    r = requests.post(f"{API}/auth/change-password", headers=_h(tok),
                      json={"current_password": "TempStart#2026", "new_password": PW[role]}, timeout=30)
    assert r.status_code == 200, r.text
    extra = {"sign_in_as": role, **({"branch_id": branch_id} if branch_id else {})}
    r = _login(email, PW[role], **extra)
    assert r.status_code == 200, r.text
    return {"email": email, "h": _h(r.json()["access_token"]), "branch": branch_id}


@pytest.fixture(scope="module")
def coord3(admin_h):
    return _make_staff(admin_h, "coordinator", "br-3")


@pytest.fixture(scope="module")
def scanner(admin_h):
    return _make_staff(admin_h, "scanner", None)


def _register(branch_id):
    tag = uuid.uuid4().hex[:6]
    email = f"delivered+olam{tag}@resend.dev"
    r = requests.post(f"{API}/registrations", json={
        "full_name": f"TEST Iter10 {tag}", "mobile": "9" + str(uuid.uuid4().int)[:9], "email": email,
        "branch_id": branch_id, "batch": "A1", "batch_no": "7", "faculty_name": "TEST Faculty",
        "confirm": True, "privacy_accepted": True}, timeout=30)
    assert r.status_code == 200, r.text
    return {"id": r.json()["id"], "reference": r.json()["reference"], "email": email}


@pytest.fixture(scope="module")
def regs():
    # 6 for bulk approve (4 br-1, 2 br-3), 1 br-3 stays pending
    return {"bulk": [_register(b) for b in ("br-1", "br-1", "br-1", "br-1", "br-3", "br-3")], "pending": _register("br-3")}


def _all_regs(admin_h):
    r = requests.get(f"{API}/registrations", headers=admin_h, timeout=30)
    assert r.status_code == 200
    return {x["id"]: x for x in r.json()}


# --- Login grammar + role/branch regression ---
class TestLogin:
    def test_admin_wrong_role_grammar(self):
        r = _login(QA["email"], QA["password"], sign_in_as="scanner")
        assert r.status_code == 403 and "This account is an Admin account" in r.json()["detail"], r.text

    def test_coord_wrong_branch(self, coord3):
        r = _login(coord3["email"], PW["coordinator"], sign_in_as="coordinator", branch_id="br-1")
        assert r.status_code == 403 and "belongs to" in r.json()["detail"], r.text

    def test_coord_as_scanner_grammar(self, coord3):
        r = _login(coord3["email"], PW["coordinator"], sign_in_as="scanner")
        assert r.status_code == 403 and "This account is a Branch Coordinator account" in r.json()["detail"], r.text


# --- Bulk approve + email retry (HIGH fix) ---
class TestBulkEmail:
    def test_coord_skip_reasons(self, coord3, regs):
        ids = [regs["bulk"][0]["id"], "nope-id"]
        r = requests.post(f"{API}/registrations/bulk-approve", headers=coord3["h"], json={"ids": ids}, timeout=30)
        assert r.status_code == 200
        assert r.json() == {"approved": 0, "skipped": [{"id": ids[0], "reason": "not your branch"}, {"id": "nope-id", "reason": "not found"}]}

    def test_bulk_approve_all_sent(self, admin_h, regs):
        ids = [x["id"] for x in regs["bulk"]]
        r = requests.post(f"{API}/registrations/bulk-approve", headers=admin_h, json={"ids": ids}, timeout=30)
        assert r.status_code == 200 and r.json()["approved"] == 6, r.text
        st = _all_regs(admin_h)
        assert all(st[i]["pass_email_status"] in ("queued", "sent") for i in ids)
        deadline = time.time() + 240
        while time.time() < deadline:
            st = _all_regs(admin_h)
            statuses = [st[i]["pass_email_status"] for i in ids]
            if all(s in ("sent", "failed") for s in statuses):
                break
            time.sleep(8)
        print("final pass_email_status:", statuses)
        assert statuses == ["sent"] * 6, statuses

    def test_already_approved_skip(self, admin_h, regs):
        i = regs["bulk"][0]["id"]
        r = requests.post(f"{API}/registrations/bulk-approve", headers=admin_h, json={"ids": [i]}, timeout=30)
        assert r.json() == {"approved": 0, "skipped": [{"id": i, "reason": "already approved"}]}


# --- Resend email RBAC ---
class TestResend:
    def test_admin_resend(self, admin_h, regs):
        i = regs["bulk"][1]["id"]
        r = requests.post(f"{API}/registrations/{i}/resend-email", headers=admin_h, timeout=30)
        assert r.status_code == 200 and r.json() == {"ok": True}
        deadline = time.time() + 90
        while time.time() < deadline:
            s = _all_regs(admin_h)[i]["pass_email_status"]
            if s != "queued":
                break
            time.sleep(4)
        assert s == "sent", s

    def test_own_branch_coord_resend(self, coord3, regs):
        r = requests.post(f"{API}/registrations/{regs['bulk'][4]['id']}/resend-email", headers=coord3["h"], timeout=30)
        assert r.status_code == 200, r.text

    def test_other_branch_coord_403(self, coord3, regs):
        r = requests.post(f"{API}/registrations/{regs['bulk'][0]['id']}/resend-email", headers=coord3["h"], timeout=30)
        assert r.status_code == 403

    def test_pending_400(self, admin_h, regs):
        r = requests.post(f"{API}/registrations/{regs['pending']['id']}/resend-email", headers=admin_h, timeout=30)
        assert r.status_code == 400

    def test_scanner_403(self, scanner, regs):
        r = requests.post(f"{API}/registrations/{regs['bulk'][0]['id']}/resend-email", headers=scanner["h"], timeout=30)
        assert r.status_code == 403

    def test_missing_404(self, admin_h):
        assert requests.post(f"{API}/registrations/nope/resend-email", headers=admin_h, timeout=30).status_code == 404


# --- Reminders ---
class TestReminders:
    BASE = {"registration_open": True, "closed_message": "Closed for now", "privacy_notice": "x" * 30}

    def test_reminders_flow(self, admin_h, regs):
        r = requests.put(f"{API}/settings", headers=admin_h, json={**self.BASE, "event_date": "2026-04-20",
                         "event_time_venue": "TEST 10 AM, Hall", "auto_reminder": False}, timeout=30)
        assert r.status_code == 200, r.text
        s = requests.get(f"{API}/reminders/status", headers=admin_h, timeout=30).json()
        assert set(s) == {"eligible", "already_sent", "pending", "failed", "sending"}, s
        assert s["pending"] >= 6 and s["sending"] is False, s
        r1 = requests.post(f"{API}/reminders/send", headers=admin_h, timeout=30)
        assert r1.status_code == 200 and r1.json()["queued"] == s["pending"], r1.text
        r2 = requests.post(f"{API}/reminders/send", headers=admin_h, timeout=30)
        assert r2.status_code == 409, r2.text
        deadline = time.time() + 300
        while time.time() < deadline:
            s = requests.get(f"{API}/reminders/status", headers=admin_h, timeout=30).json()
            if not s["sending"]:
                break
            time.sleep(8)
        print("reminder status after send:", s)
        assert s["sending"] is False and s["pending"] == 0 and s["failed"] == 0, s

    def test_coord_forbidden(self, coord3):
        assert requests.get(f"{API}/reminders/status", headers=coord3["h"], timeout=30).status_code == 403
        assert requests.post(f"{API}/reminders/send", headers=coord3["h"], timeout=30).status_code == 403


# --- Regression: scan ---
class TestScan:
    def test_scan_valid_then_duplicate(self, scanner, regs):
        x = regs["bulk"][2]
        tok = requests.post(f"{API}/registrations/lookup", json={"reference": x["reference"], "email": x["email"]}, timeout=30).json()["pass_token"]
        r1 = requests.post(f"{API}/scan", headers=scanner["h"], json={"token": tok, "station": "TEST-gate"}, timeout=30).json()
        r2 = requests.post(f"{API}/scan", headers=scanner["h"], json={"token": tok, "station": "TEST-gate"}, timeout=30).json()
        assert r1["result"] == "VALID" and r2["result"] == "ALREADY_CHECKED_IN", (r1, r2)
