# OLAM 3.0 iteration-9: sign-in role/branch check, coordinator branch isolation, bulk approve, pass reminder emails
# Restart backend before running (in-memory rate limits). Uses only @resend.dev emails.
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
COORD_PW = "CoordNew#2026x"
SCAN_PW = "ScanNew#2026x"


def _login(email, pw, **extra):
    return requests.post(f"{API}/auth/login", json={"email": email, "password": pw, **extra}, timeout=30)


def _h(tok):
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="module")
def admin_h():
    r = _login(QA["email"], QA["password"])
    assert r.status_code == 200, r.text
    return _h(r.json()["access_token"])


def _make_staff(admin_h, role, branch_id, final_pw):
    email = f"test_{role}_{uuid.uuid4().hex[:6]}@olam.delta"
    body = {"email": email, "password": "TempStart#2026", "name": f"TEST {role}", "role": role}
    if branch_id:
        body["branch_id"] = branch_id
    r = requests.post(f"{API}/staff", headers=admin_h, json=body, timeout=30)
    assert r.status_code == 200, r.text
    tok = _login(email, "TempStart#2026").json()["access_token"]
    r = requests.post(f"{API}/auth/change-password", headers=_h(tok),
                      json={"current_password": "TempStart#2026", "new_password": final_pw}, timeout=30)
    assert r.status_code == 200, r.text
    return {"email": email, "id": None}


@pytest.fixture(scope="module")
def coord(admin_h):
    s = _make_staff(admin_h, "coordinator", "br-3", COORD_PW)
    r = _login(s["email"], COORD_PW, sign_in_as="coordinator", branch_id="br-3")
    assert r.status_code == 200, r.text
    s["h"] = _h(r.json()["access_token"])
    return s


@pytest.fixture(scope="module")
def scanner(admin_h):
    s = _make_staff(admin_h, "scanner", None, SCAN_PW)
    s["h"] = _h(_login(s["email"], SCAN_PW).json()["access_token"])
    return s


def _register(branch_id):
    tag = uuid.uuid4().hex[:6]
    email = f"delivered+olam{tag}@resend.dev"
    r = requests.post(f"{API}/registrations", json={
        "full_name": f"TEST Iter9 {tag}", "mobile": "9" + str(uuid.uuid4().int)[:9], "email": email,
        "branch_id": branch_id, "batch": "A1", "batch_no": "7", "faculty_name": "TEST Faculty",
        "confirm": True, "privacy_accepted": True}, timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    return {"id": d["id"], "reference": d["reference"], "email": email}


@pytest.fixture(scope="module")
def regs():
    return {"b1": _register("br-1"), "b3a": _register("br-3"), "b3b": _register("br-3"),
            "b2": _register("br-2"), "b1x": _register("br-1")}


# --- Login: sign_in_as + branch_id ---
class TestLoginRole:
    def test_admin_no_role_backward_compat(self):
        assert _login(QA["email"], QA["password"]).status_code == 200

    def test_admin_correct_role(self):
        r = _login(QA["email"], QA["password"], sign_in_as="super_admin")
        assert r.status_code == 200 and r.json()["user"]["role"] == "super_admin"

    def test_admin_wrong_role_403(self):
        r = _login(QA["email"], QA["password"], sign_in_as="coordinator", branch_id="br-1")
        assert r.status_code == 403 and "Admin" in r.json()["detail"], r.text

    def test_coord_wrong_branch_403(self, coord):
        r = _login(coord["email"], COORD_PW, sign_in_as="coordinator", branch_id="br-1")
        assert r.status_code == 403 and "MUVATTUPUZHA" in r.json()["detail"], r.text

    def test_coord_missing_branch_403(self, coord):
        r = _login(coord["email"], COORD_PW, sign_in_as="coordinator")
        assert r.status_code == 403, r.text

    def test_coord_as_scanner_403(self, coord):
        r = _login(coord["email"], COORD_PW, sign_in_as="scanner")
        assert r.status_code == 403 and "Branch Coordinator" in r.json()["detail"], r.text

    def test_scanner_correct_role(self, scanner):
        assert _login(scanner["email"], SCAN_PW, sign_in_as="scanner").status_code == 200

    def test_wrong_password_no_hints(self, coord):
        r = _login(coord["email"], "WrongPass#999", sign_in_as="coordinator", branch_id="br-1")
        assert r.status_code == 401 and r.json()["detail"] == "Invalid credentials", r.text

    def test_invalid_sign_in_as_422(self):
        assert _login(QA["email"], QA["password"], sign_in_as="student").status_code == 422


# --- Branch isolation ---
class TestBranchIsolation:
    def test_coord_cannot_list_other_branch(self, coord, regs):
        r = requests.get(f"{API}/registrations", headers=coord["h"], params={"branch_id": "br-1"}, timeout=30)
        assert r.status_code == 200
        ids = {x["id"] for x in r.json()}
        assert regs["b1"]["id"] not in ids and all(x["branch_id"] == "br-3" for x in r.json())
        assert regs["b3a"]["id"] in ids

    def test_coord_cannot_approve_other_branch(self, coord, regs):
        r = requests.post(f"{API}/registrations/{regs['b1x']['id']}/approve", headers=coord["h"], timeout=30)
        assert r.status_code == 403, r.text

    def test_coord_cannot_reject_other_branch(self, coord, regs):
        r = requests.post(f"{API}/registrations/{regs['b1x']['id']}/reject", headers=coord["h"],
                          json={"reason": "TEST nope"}, timeout=30)
        assert r.status_code == 403, r.text


# --- Bulk approve ---
class TestBulkApprove:
    def test_validation(self, admin_h, scanner):
        assert requests.post(f"{API}/registrations/bulk-approve", headers=admin_h, json={"ids": []}, timeout=30).status_code == 422
        assert requests.post(f"{API}/registrations/bulk-approve", headers=admin_h,
                             json={"ids": [f"x{i}" for i in range(201)]}, timeout=30).status_code == 422
        assert requests.post(f"{API}/registrations/bulk-approve", headers=scanner["h"], json={"ids": ["x"]}, timeout=30).status_code == 403

    def test_coord_bulk(self, coord, regs):
        ids = [regs["b3a"]["id"], regs["b1"]["id"], "nonexistent-id"]
        r = requests.post(f"{API}/registrations/bulk-approve", headers=coord["h"], json={"ids": ids}, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["approved"] == 1
        reasons = {s["id"]: s["reason"] for s in d["skipped"]}
        assert reasons[regs["b1"]["id"]] == "not your branch"
        assert reasons["nonexistent-id"] == "not found"

    def test_admin_bulk_cross_branch_and_skip_approved(self, admin_h, regs):
        ids = [regs["b1"]["id"], regs["b2"]["id"], regs["b3b"]["id"], regs["b3a"]["id"]]
        r = requests.post(f"{API}/registrations/bulk-approve", headers=admin_h, json={"ids": ids}, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["approved"] == 3
        assert d["skipped"] == [{"id": regs["b3a"]["id"], "reason": "already approved"}]

    def test_approved_have_pass(self, regs):
        for k in ("b1", "b2", "b3a", "b3b"):
            r = requests.post(f"{API}/registrations/lookup", json={"reference": regs[k]["reference"], "email": regs[k]["email"]}, timeout=30)
            assert r.status_code == 200, r.text
            assert r.json()["registration"]["status"] == "approved" and r.json()["pass_token"], k

    def test_rejected_skipped(self, admin_h, regs):
        r = requests.post(f"{API}/registrations/{regs['b1x']['id']}/reject", headers=admin_h, json={"reason": "TEST reject"}, timeout=30)
        assert r.status_code == 200, r.text
        r = requests.post(f"{API}/registrations/bulk-approve", headers=admin_h, json={"ids": [regs["b1x"]["id"]]}, timeout=30)
        assert r.json() == {"approved": 0, "skipped": [{"id": regs["b1x"]["id"], "reason": "already rejected"}]}


# --- Settings + reminders ---
class TestReminders:
    BASE = {"registration_open": True, "closed_message": "Closed for now", "privacy_notice": "x" * 30}

    def test_invalid_dates_422(self, admin_h):
        for bad in ("2026-13-40", "20-12-2026", "2026/12/20"):
            r = requests.put(f"{API}/settings", headers=admin_h, json={**self.BASE, "event_date": bad}, timeout=30)
            assert r.status_code == 422, (bad, r.status_code)

    def test_save_settings(self, admin_h):
        r = requests.put(f"{API}/settings", headers=admin_h, json={**self.BASE, "event_date": "2026-03-15",
                         "event_time_venue": "TEST 10 AM, Hall", "auto_reminder": False}, timeout=30)
        assert r.status_code == 200, r.text
        g = requests.get(f"{API}/settings", headers=admin_h, timeout=30).json()
        assert g["event_date"] == "2026-03-15" and g["event_time_venue"] == "TEST 10 AM, Hall" and g["auto_reminder"] is False

    def test_coord_forbidden(self, coord):
        assert requests.get(f"{API}/reminders/status", headers=coord["h"], timeout=30).status_code == 403
        assert requests.post(f"{API}/reminders/send", headers=coord["h"], timeout=30).status_code == 403

    def test_send_and_status(self, admin_h, regs):
        st = requests.get(f"{API}/reminders/status", headers=admin_h, timeout=30).json()
        print("status before", st)
        assert st["eligible"] >= 4 and st["pending"] >= 1
        q = requests.post(f"{API}/reminders/send", headers=admin_h, timeout=30).json()
        assert q["queued"] == st["pending"]
        for _ in range(30):
            time.sleep(2)
            st2 = requests.get(f"{API}/reminders/status", headers=admin_h, timeout=30).json()
            if st2["pending"] == 0:
                break
        print("status after", st2)
        assert st2["pending"] == 0 and st2["already_sent"] == st2["eligible"]
        assert requests.post(f"{API}/reminders/send", headers=admin_h, timeout=30).json()["queued"] == 0


# --- Regression: scan ---
class TestScanRegression:
    def test_scan_valid_then_duplicate(self, scanner, regs):
        tok = requests.post(f"{API}/registrations/lookup", json={"reference": regs["b2"]["reference"], "email": regs["b2"]["email"]}, timeout=30).json()["pass_token"]
        r1 = requests.post(f"{API}/scan", headers=scanner["h"], json={"token": tok, "station": "TEST-gate"}, timeout=30).json()
        r2 = requests.post(f"{API}/scan", headers=scanner["h"], json={"token": tok, "station": "TEST-gate"}, timeout=30).json()
        assert r1["result"] == "VALID" and r2["result"] == "ALREADY_CHECKED_IN", (r1, r2)

    def test_privacy_required(self):
        r = requests.post(f"{API}/registrations", json={
            "full_name": "TEST NoPrivacy", "mobile": "9876500000", "email": "delivered@resend.dev", "branch_id": "br-1",
            "batch": "A1", "batch_no": "1", "faculty_name": "TEST F", "confirm": True, "privacy_accepted": False}, timeout=30)
        assert r.status_code == 422
