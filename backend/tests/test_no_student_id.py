# Iteration 7: Student ID removed; new duplicate rule (branch + last-10 mobile digits + normalised name)
import os
import time
import uuid
import csv
import io
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL") or os.environ.get("EXPO_BACKEND_URL")
if not BASE_URL:
    for line in open("/app/frontend/.env"):
        if line.startswith("EXPO_PUBLIC_BACKEND_URL=") or line.startswith("EXPO_BACKEND_URL="):
            BASE_URL = line.split("=", 1)[1].strip().strip('"')
API = BASE_URL.rstrip("/") + "/api"
EMAIL = "delivered@resend.dev"
OLD_REFS = ["OLM-8932B1", "OLM-E9C76C", "OLM-72857B", "OLM-E04B9A", "OLM-7A2076"]


def _post(path, **kw):
    r = requests.post(f"{API}{path}", timeout=60, **kw)
    if r.status_code == 429:
        time.sleep(61)
        r = requests.post(f"{API}{path}", timeout=60, **kw)
    return r


def _mobile():
    return "9" + str(uuid.uuid4().int)[:9]


def _payload(**over):
    p = {"full_name": "TEST NoId " + uuid.uuid4().hex[:6], "mobile": _mobile(), "email": EMAIL,
         "branch_id": "br-1", "batch": "TEST_Batch", "batch_no": "B-7", "faculty_name": "TEST Faculty Seven",
         "confirm": True}
    p.update(over)
    return p


@pytest.fixture(scope="module")
def admin():
    r = _post("/auth/login", json={"email": "qa-admin@olam.delta", "password": "QaAdmin#2026x"})
    if r.status_code != 200:
        pytest.skip(f"QA admin login failed {r.status_code}")
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


# --- Registration without student_code
class TestNoStudentId:
    def test_register_without_student_code(self):
        r = _post("/registrations", json=_payload())
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["student_code"] is None and d["reference"].startswith("OLM-")

    def test_student_code_ignored(self, admin):
        r = _post("/registrations", json=_payload(student_code="TEST_SHOULD_IGNORE"))
        assert r.status_code == 200, r.text
        assert r.json()["student_code"] is None
        lst = requests.get(f"{API}/registrations", params={"q": r.json()["reference"]}, headers=admin, timeout=30).json()
        assert len(lst) == 1 and lst[0]["student_code"] is None


# --- New duplicate rule
class TestDuplicateRule:
    def test_same_branch_mobile_name_409(self):
        m = _mobile()
        name = "TEST Dup Person " + uuid.uuid4().hex[:4]
        assert _post("/registrations", json=_payload(full_name=name, mobile=m)).status_code == 200
        r = _post("/registrations", json=_payload(full_name="  " + name.upper().replace(" ", "   ") + " ",
                                                   mobile=f"+91 {m[:5]} {m[5:]}"))
        assert r.status_code == 409, r.text
        assert "already registered" in r.json()["detail"].lower()

    def test_sibling_same_mobile_200(self):
        m = _mobile()
        assert _post("/registrations", json=_payload(full_name="TEST Sib A " + uuid.uuid4().hex[:4], mobile=m)).status_code == 200
        r = _post("/registrations", json=_payload(full_name="TEST Sib B " + uuid.uuid4().hex[:4], mobile=m))
        assert r.status_code == 200, r.text

    def test_same_name_mobile_other_branch_200(self):
        m = _mobile()
        name = "TEST Cross " + uuid.uuid4().hex[:4]
        assert _post("/registrations", json=_payload(full_name=name, mobile=m, branch_id="br-1")).status_code == 200
        r = _post("/registrations", json=_payload(full_name=name, mobile=m, branch_id="br-2"))
        assert r.status_code == 200, r.text


# --- Admin dashboard data: old regs, search, CSV
class TestAdminViews:
    def test_old_regs_listed(self, admin):
        r = requests.get(f"{API}/registrations", headers=admin, timeout=60)
        assert r.status_code == 200, r.text
        refs = {x["reference"] for x in r.json()}
        missing = [x for x in OLD_REFS if x not in refs]
        assert not missing, f"missing old refs {missing}"

    def test_search_name_phone_faculty(self, admin):
        m = _mobile()
        name = "TEST Searchable " + uuid.uuid4().hex[:6]
        fac = "TEST Fac " + uuid.uuid4().hex[:6]
        ref = _post("/registrations", json=_payload(full_name=name, mobile=m, faculty_name=fac)).json()["reference"]
        for q in [name.lower(), m, fac]:
            lst = requests.get(f"{API}/registrations", params={"q": q}, headers=admin, timeout=30).json()
            assert ref in [x["reference"] for x in lst], f"search {q!r} failed"

    def test_csv_columns(self, admin):
        r = requests.get(f"{API}/export/registrations.csv", headers=admin, timeout=60)
        assert r.status_code == 200
        header = next(csv.reader(io.StringIO(r.text)))
        assert "Student ID" not in header
        assert "Batch No." in header and "Faculty Name" in header


# --- Regression: approve -> lookup -> scan VALID then ALREADY_CHECKED_IN
class TestPassRegression:
    def test_approve_lookup_scan(self, admin):
        reg = _post("/registrations", json=_payload()).json()
        a = _post(f"/registrations/{reg['id']}/approve", headers=admin)
        assert a.status_code == 200 and a.json()["status"] == "approved"
        lk = _post("/registrations/lookup", json={"reference": reg["reference"], "email": EMAIL})
        assert lk.status_code == 200
        token = lk.json()["pass_token"]
        assert token
        s1 = _post("/scan", json={"token": token}, headers=admin)
        assert s1.status_code == 200 and s1.json()["result"] == "VALID", s1.text
        s2 = _post("/scan", json={"token": token}, headers=admin)
        assert s2.json()["result"] == "ALREADY_CHECKED_IN", s2.text
