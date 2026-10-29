# OLAM 3.0 iteration-8: Event settings (open/close + privacy notice), privacy_accepted on registration, Faculty report + CSV
import csv
import io
import os
import re
import uuid
import pytest
import requests
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")
BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
ADMIN = {"email": "qa-admin@olam.delta", "password": "QaAdmin#2026x"}
PW = "TestPass@123"
NEWPW = "TestPassNew2026"
mdb = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def _login(email, pw):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw}, timeout=30)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _reg_payload(**kw):
    p = {"full_name": "TEST Fac Student " + uuid.uuid4().hex[:4], "mobile": "9" + str(uuid.uuid4().int)[:9],
         "email": "delivered@resend.dev", "branch_id": "br-1", "batch": "TEST_Batch", "batch_no": "B12",
         "faculty_name": "TEST Faculty", "confirm": True, "privacy_accepted": True}
    p.update(kw)
    return p


def _register(**kw):
    r = requests.post(f"{API}/registrations", json=_reg_payload(**kw), timeout=30)
    if r.status_code == 429:
        pytest.skip("rate limited")
    return r


@pytest.fixture(scope="module")
def admin():
    return _login(ADMIN["email"], ADMIN["password"])


@pytest.fixture(scope="module")
def staff(admin):
    sfx = uuid.uuid4().hex[:6]
    out = {}
    for key, role, br, exp in (("coord", "coordinator", "br-1", False), ("coord_exp", "coordinator", "br-1", True), ("scanner", "scanner", None, False)):
        email = f"test_fac_{key}_{sfx}@olam.delta"
        r = requests.post(f"{API}/staff", headers=admin, json={"email": email, "password": PW, "name": f"TEST {key}", "role": role, "branch_id": br, "can_export": exp}, timeout=30)
        assert r.status_code == 200, r.text
        h = _login(email, PW)
        c = requests.post(f"{API}/auth/change-password", headers=h, json={"current_password": PW, "new_password": NEWPW}, timeout=30)
        assert c.status_code == 200, c.text
        out[key] = {"id": r.json()["id"], "h": _login(email, NEWPW)}
    yield out
    for u in out.values():
        requests.patch(f"{API}/staff/{u['id']}", headers=admin, json={"active": False}, timeout=30)


@pytest.fixture(scope="module", autouse=True)
def restore_settings():
    yield
    mdb.settings.delete_many({})  # default: registration open + default notice


# --- Settings ---
class TestSettings:
    def test_public_defaults(self):
        mdb.settings.delete_many({})
        r = requests.get(f"{API}/public/settings", timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert d["registration_open"] is True and len(d["closed_message"]) > 3 and len(d["privacy_notice"]) > 20
        assert set(d.keys()) == {"registration_open", "closed_message", "privacy_notice"}

    def test_settings_rbac(self, admin, staff):
        assert requests.get(f"{API}/settings", headers=admin, timeout=30).status_code == 200
        for k in ("coord", "scanner"):
            assert requests.get(f"{API}/settings", headers=staff[k]["h"], timeout=30).status_code == 403
            assert requests.put(f"{API}/settings", headers=staff[k]["h"], json={"registration_open": False, "closed_message": "Closed now", "privacy_notice": "x" * 30}, timeout=30).status_code == 403
        assert requests.get(f"{API}/settings", timeout=30).status_code in (401, 403)

    def test_short_messages_422(self, admin):
        r1 = requests.put(f"{API}/settings", headers=admin, json={"registration_open": True, "closed_message": "ab", "privacy_notice": "x" * 30}, timeout=30)
        r2 = requests.put(f"{API}/settings", headers=admin, json={"registration_open": True, "closed_message": "Closed", "privacy_notice": "too short"}, timeout=30)
        assert r1.status_code == 422 and r2.status_code == 422

    def test_close_blocks_then_reopen(self, admin):
        msg = "TEST_ Registration closed for testing"
        notice = "TEST_ privacy notice for automated testing purposes only."
        r = requests.put(f"{API}/settings", headers=admin, json={"registration_open": False, "closed_message": msg, "privacy_notice": notice}, timeout=30)
        assert r.status_code == 200 and r.json()["registration_open"] is False and r.json()["updated_by_name"]
        pub = requests.get(f"{API}/public/settings", timeout=30).json()
        assert pub == {"registration_open": False, "closed_message": msg, "privacy_notice": notice}
        b = _register()
        assert b.status_code == 403 and b.json()["detail"] == msg
        r = requests.put(f"{API}/settings", headers=admin, json={"registration_open": True, "closed_message": msg, "privacy_notice": notice}, timeout=30)
        assert r.status_code == 200 and r.json()["registration_open"] is True
        ok = _register()
        assert ok.status_code == 200, ok.text
        mdb.registrations.delete_one({"id": ok.json()["id"]})


# --- Registration privacy_accepted ---
class TestPrivacyAccepted:
    def test_false_422(self):
        assert _register(privacy_accepted=False).status_code == 422

    def test_missing_422(self):
        p = _reg_payload()
        p.pop("privacy_accepted")
        r = requests.post(f"{API}/registrations", json=p, timeout=30)
        assert r.status_code == 422

    def test_true_ok_and_timestamp(self):
        r = _register()
        assert r.status_code == 200, r.text
        doc = mdb.registrations.find_one({"id": r.json()["id"]})
        assert doc.get("privacy_accepted_at") is not None
        mdb.registrations.delete_one({"id": doc["id"]})


# --- Faculty report ---
@pytest.fixture(scope="module")
def fac_regs(admin):
    tag = uuid.uuid4().hex[:5]
    ids = []
    for fname, br in (("TEST Ms Rani" + tag, "br-1"), ("  test  ms   rani" + tag.upper() + " ", "br-1"), ("TEST Ms Rani" + tag, "br-2"), ("=cmd|' /C calc'!A0" + tag, "br-1")):
        r = _register(faculty_name=fname, branch_id=br)
        assert r.status_code == 200, r.text
        ids.append(r.json()["id"])
    # approve the first; reject the third
    assert requests.post(f"{API}/registrations/{ids[0]}/approve", headers=admin, timeout=60).status_code == 200
    rj = requests.post(f"{API}/registrations/{ids[2]}/reject", headers=admin, json={"reason": "TEST reject"}, timeout=30)
    assert rj.status_code == 200, rj.text
    yield {"tag": tag, "ids": ids}
    mdb.registrations.delete_many({"id": {"$in": ids}})
    mdb.attendance.delete_many({"registration_id": {"$in": ids}})


def _row(rows, branch_id, tag):
    return [r for r in rows if r["branch_id"] == branch_id and r["faculty_name"].lower().startswith("test ms rani") and r["faculty_name"].lower().endswith(tag.lower())]


class TestFacultyReport:
    def test_grouping_case_space_insensitive(self, admin, fac_regs):
        d = requests.get(f"{API}/reports/faculty", headers=admin, timeout=30).json()
        br1 = _row(d["rows"], "br-1", fac_regs["tag"])
        br2 = _row(d["rows"], "br-2", fac_regs["tag"])
        assert len(br1) == 1 and br1[0]["total"] == 2 and br1[0]["approved"] == 1 and br1[0]["pending"] == 1
        assert len(br2) == 1 and br2[0]["total"] == 1 and br2[0]["rejected"] == 1
        assert d["faculty_count"] == len(d["rows"]) and d["total_students"] == sum(r["total"] for r in d["rows"])

    def test_totals_match_db(self, admin, fac_regs):
        d = requests.get(f"{API}/reports/faculty", headers=admin, timeout=30).json()
        db_total = mdb.registrations.count_documents({"faculty_name": {"$exists": True, "$nin": [None, ""]}})
        assert d["total_students"] == db_total
        for s in ("approved", "pending", "rejected"):
            assert sum(r[s] for r in d["rows"]) == mdb.registrations.count_documents({"faculty_name": {"$exists": True, "$nin": [None, ""]}, "status": s})
        checked_ids = {a["registration_id"] for a in mdb.attendance.find({}, {"registration_id": 1})}
        db_checked = mdb.registrations.count_documents({"faculty_name": {"$exists": True, "$nin": [None, ""]}, "id": {"$in": list(checked_ids)}})
        assert sum(r["checked_in"] for r in d["rows"]) == db_checked

    def test_admin_branch_filter(self, admin, fac_regs):
        d = requests.get(f"{API}/reports/faculty?branch_id=br-2", headers=admin, timeout=30).json()
        assert d["rows"] and all(r["branch_id"] == "br-2" for r in d["rows"])

    def test_coordinator_own_branch_only(self, staff, fac_regs):
        d = requests.get(f"{API}/reports/faculty?branch_id=br-2", headers=staff["coord"]["h"], timeout=30)
        assert d.status_code == 200
        assert d.json()["rows"] and all(r["branch_id"] == "br-1" for r in d.json()["rows"])

    def test_scanner_403(self, staff):
        assert requests.get(f"{API}/reports/faculty", headers=staff["scanner"]["h"], timeout=30).status_code == 403
        assert requests.get(f"{API}/export/faculty.csv", headers=staff["scanner"]["h"], timeout=30).status_code == 403

    def test_csv_admin(self, admin, fac_regs):
        r = requests.get(f"{API}/export/faculty.csv", headers=admin, timeout=30)
        assert r.status_code == 200 and "text/csv" in r.headers["content-type"]
        rows = list(csv.reader(io.StringIO(r.text)))
        assert rows[0] == ["Branch", "Faculty Name", "Total Students", "Approved", "Pending", "Rejected", "Checked In"]
        evil = [x for x in rows if fac_regs["tag"] in x[1] and "cmd" in x[1]]
        assert evil and evil[0][1].startswith("'"), evil

    def test_csv_coordinator_perm(self, staff, fac_regs):
        assert requests.get(f"{API}/export/faculty.csv", headers=staff["coord"]["h"], timeout=30).status_code == 403
        r = requests.get(f"{API}/export/faculty.csv?branch_id=br-2", headers=staff["coord_exp"]["h"], timeout=30)
        assert r.status_code == 200
        rows = list(csv.reader(io.StringIO(r.text)))[1:]
        br1_name = mdb.branches.find_one({"id": "br-1"})["name"]
        assert rows and all(x[0] == br1_name for x in rows)


# --- Regression approve -> scan ---
class TestScanRegression:
    def test_approve_scan(self, admin):
        r = _register()
        assert r.status_code == 200, r.text
        reg = r.json()
        try:
            assert requests.post(f"{API}/registrations/{reg['id']}/approve", headers=admin, timeout=60).status_code == 200
            lk = requests.post(f"{API}/registrations/lookup", json={"reference": reg["reference"], "email": "delivered@resend.dev"}, timeout=30).json()
            tok = lk["pass_token"]
            s1 = requests.post(f"{API}/scan", json={"token": tok}, headers=admin, timeout=30).json()
            s2 = requests.post(f"{API}/scan", json={"token": tok}, headers=admin, timeout=30).json()
            assert s1["result"] == "VALID" and s2["result"] == "ALREADY_CHECKED_IN"
        finally:
            mdb.registrations.delete_one({"id": reg["id"]})
            mdb.attendance.delete_many({"registration_id": reg["id"]})
