# OLAM 3.0 iteration 16: Absent (not-arrived) report /reports/absent + CSV /export/absent.csv
import csv
import io
import uuid
import pytest
import requests
from test_olam_api import API, _login, admin, staff, STAFF_PW, STAFF_NEW_PW  # noqa: F401
from test_olam_api import _post_rl

BATCH = "TEST_ABS_" + uuid.uuid4().hex[:6]


def _reg(branch, tag):
    r = _post_rl(f"{API}/registrations", json={
        "full_name": f"TEST ABS {tag} {uuid.uuid4().hex[:4]}", "mobile": "9" + str(uuid.uuid4().int)[:9],
        "email": "delivered@resend.dev", "branch_id": branch, "batch": BATCH, "batch_no": "B7",
        "faculty_name": "TEST FacultyAbs", "confirm": True, "privacy_accepted": True})
    assert r.status_code == 200, r.text
    return r.json()


def _absent(h, params=None):
    r = requests.get(f"{API}/reports/absent", headers=h, params=params, timeout=60)
    assert r.status_code == 200, r.text
    return r.json()


def _refs(data):
    return {s["reference"] for g in data["branches"] for s in g["students"]}


@pytest.fixture(scope="module")
def branch_names(admin):
    return {b["id"]: b["name"] for b in requests.get(f"{API}/branches", headers=admin, timeout=30).json()}


@pytest.fixture(scope="module")
def ds(admin, staff):
    """br-1: approved-absent, approved-scanned, pending, rejected; br-2: approved-absent."""
    a1, a2, p1, r1 = _reg("br-1", "A1"), _reg("br-1", "A2"), _reg("br-1", "P1"), _reg("br-1", "R1")
    b1 = _reg("br-2", "B1")
    for x in (a1, a2, b1):
        assert requests.post(f"{API}/registrations/{x['id']}/approve", headers=admin, timeout=60).status_code == 200
    rj = requests.post(f"{API}/registrations/{r1['id']}/reject", headers=admin, json={"reason": "TEST reject"}, timeout=60)
    assert rj.status_code == 200, rj.text
    s = requests.post(f"{API}/scan", headers=staff["scanner"], json={"token": a2["reference"], "station": "TEST"}, timeout=30).json()
    assert s["result"] == "VALID", s
    return {"a1": a1, "a2": a2, "p1": p1, "r1": r1, "b1": b1}


class TestAbsentReport:
    def test_shape_and_fields(self, admin, ds, branch_names):
        d = _absent(admin)
        assert isinstance(d["total"], int) and isinstance(d["branches"], list)
        assert d["total"] == sum(g["count"] for g in d["branches"])
        for g in d["branches"]:
            assert g["count"] == len(g["students"])
        stu = next(s for g in d["branches"] for s in g["students"] if s["reference"] == ds["a1"]["reference"])
        for k in ("reference", "full_name", "mobile", "email", "batch", "batch_no", "faculty_name"):
            assert k in stu, k
        assert stu["batch"] == BATCH and stu["batch_no"] == "B7" and stu["faculty_name"] == "TEST FacultyAbs"
        assert "_id" not in stu
        grp = next(g for g in d["branches"] if any(s["reference"] == ds["a1"]["reference"] for s in g["students"]))
        assert grp["branch_name"] == branch_names["br-1"]

    def test_inclusion_exclusion(self, admin, ds):
        refs = _refs(_absent(admin))
        assert ds["a1"]["reference"] in refs and ds["b1"]["reference"] in refs
        assert ds["a2"]["reference"] not in refs, "checked-in student must be excluded"
        assert ds["p1"]["reference"] not in refs, "pending excluded"
        assert ds["r1"]["reference"] not in refs, "rejected excluded"

    def test_admin_branch_filter(self, admin, ds, branch_names):
        d = _absent(admin, {"branch_id": "br-2"})
        assert {g["branch_name"] for g in d["branches"]} <= {branch_names["br-2"]}
        refs = _refs(d)
        assert ds["b1"]["reference"] in refs and ds["a1"]["reference"] not in refs

    def test_coordinator_scoped_and_param_ignored(self, staff, ds, branch_names):
        for params in (None, {"branch_id": "br-2"}):
            d = _absent(staff["coordinator"], params)
            assert {g["branch_name"] for g in d["branches"]} <= {branch_names["br-1"]}
            refs = _refs(d)
            assert ds["a1"]["reference"] in refs and ds["b1"]["reference"] not in refs

    def test_scan_removes_from_list(self, admin, staff, ds):
        assert ds["b1"]["reference"] in _refs(_absent(admin))
        s = requests.post(f"{API}/scan", headers=staff["scanner"], json={"token": ds["b1"]["reference"], "station": "TEST"}, timeout=30).json()
        assert s["result"] == "VALID"
        assert ds["b1"]["reference"] not in _refs(_absent(admin))

    def test_scanner_forbidden(self, staff):
        assert requests.get(f"{API}/reports/absent", headers=staff["scanner"], timeout=30).status_code == 403

    def test_unauthenticated(self):
        assert requests.get(f"{API}/reports/absent", timeout=30).status_code in (401, 403)


class TestAbsentCsv:
    def test_admin_csv(self, admin, ds, branch_names):
        r = requests.get(f"{API}/export/absent.csv", headers=admin, timeout=60)
        assert r.status_code == 200 and "text/csv" in r.headers["content-type"]
        assert "olam-absent-students.csv" in r.headers.get("content-disposition", "")
        rows = list(csv.reader(io.StringIO(r.text)))
        assert rows[0] == ["Branch", "Reference", "Name", "Mobile", "Email", "Batch", "Batch No.", "Faculty Name"]
        row = next(x for x in rows if x[1] == ds["a1"]["reference"])
        assert row[0] == branch_names["br-1"] and row[5] == BATCH and row[6] == "B7"
        refs = {x[1] for x in rows[1:]}
        assert ds["a2"]["reference"] not in refs and ds["p1"]["reference"] not in refs
        assert len(rows) - 1 == _absent(admin)["total"]

    def test_admin_csv_branch_filter(self, admin, ds, branch_names):
        r = requests.get(f"{API}/export/absent.csv", headers=admin, params={"branch_id": "br-1"}, timeout=60)
        rows = list(csv.reader(io.StringIO(r.text)))[1:]
        assert rows and all(x[0] == branch_names["br-1"] for x in rows)

    def test_coordinator_without_export_403(self, staff):
        assert requests.get(f"{API}/export/absent.csv", headers=staff["coordinator"], timeout=30).status_code == 403

    def test_scanner_403(self, staff):
        assert requests.get(f"{API}/export/absent.csv", headers=staff["scanner"], timeout=30).status_code == 403

    def test_coordinator_with_export_scoped(self, admin, branch_names, ds):
        email = f"test_coordabs_{uuid.uuid4().hex[:6]}@olam.delta"
        r = requests.post(f"{API}/staff", headers=admin, json={"email": email, "password": STAFF_PW, "name": "TEST coordabs",
                                                             "role": "coordinator", "branch_id": "br-1", "can_export": True}, timeout=30)
        assert r.status_code == 200, r.text
        h = _login(email, STAFF_PW)
        assert requests.post(f"{API}/auth/change-password", headers=h, json={"current_password": STAFF_PW, "new_password": STAFF_NEW_PW}, timeout=30).status_code == 200
        h = _login(email, STAFF_NEW_PW)
        c = requests.get(f"{API}/export/absent.csv", headers=h, params={"branch_id": "br-2"}, timeout=60)
        assert c.status_code == 200, c.text
        rows = list(csv.reader(io.StringIO(c.text)))[1:]
        assert rows and all(x[0] == branch_names["br-1"] for x in rows)
