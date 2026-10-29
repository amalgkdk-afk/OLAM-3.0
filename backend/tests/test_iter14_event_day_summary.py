# OLAM 3.0 iteration 14: Event Day Summary report (/reports/event-day) + CSV export (/export/event-day.csv) + scan welcome payload
import csv
import io
import uuid
import pytest
import requests
from test_olam_api import API, _login, admin, staff, STAFF_PW, STAFF_NEW_PW  # noqa: F401
from test_olam_api import _post_rl

BATCH = "TEST_EDS_" + uuid.uuid4().hex[:6]


def _reg(branch):
    r = _post_rl(f"{API}/registrations", json={
        "full_name": f"TEST EDS {uuid.uuid4().hex[:4]}", "mobile": "9" + str(uuid.uuid4().int)[:9],
        "email": "delivered@resend.dev", "branch_id": branch, "batch": BATCH, "batch_no": "B1",
        "faculty_name": "TEST Faculty", "confirm": True, "privacy_accepted": True})
    assert r.status_code == 200, r.text
    return r.json()


def _approve(h, rid):
    r = requests.post(f"{API}/registrations/{rid}/approve", headers=h, timeout=60)
    assert r.status_code == 200, r.text


def _summary(h):
    r = requests.get(f"{API}/reports/event-day", headers=h, timeout=60)
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture(scope="module")
def branch_names(admin):
    return {b["id"]: b["name"] for b in requests.get(f"{API}/branches", headers=admin, timeout=30).json()}


@pytest.fixture(scope="module")
def dataset(admin, staff):
    """3 regs br-1 (2 approved, 1 scanned) + 1 reg br-2 (approved) all in a unique batch."""
    before = _summary(admin)["totals"]
    a1, a2, p1 = _reg("br-1"), _reg("br-1"), _reg("br-1")
    b1 = _reg("br-2")
    for r in (a1, a2, b1):
        _approve(admin, r["id"])
    scan = requests.post(f"{API}/scan", headers=staff["scanner"], json={"token": a1["reference"], "station": "TEST"}, timeout=30)
    assert scan.status_code == 200, scan.text
    return {"before": before, "a1": a1, "a2": a2, "p1": p1, "b1": b1, "scan": scan.json()}


# --- Scan payload used by welcome card
class TestScanWelcomePayload:
    def test_valid_scan_has_name_and_branch(self, dataset, branch_names):
        s = dataset["scan"]
        assert s["result"] == "VALID", s
        reg = s["registration"]
        assert reg["full_name"] == dataset["a1"]["full_name"]
        assert reg["branch_name"] == branch_names["br-1"]
        assert reg["batch"] == BATCH and reg["reference"] == dataset["a1"]["reference"]
        assert s.get("checked_in_at")

    def test_duplicate_scan(self, dataset, staff):
        r = requests.post(f"{API}/scan", headers=staff["scanner"], json={"token": dataset["a1"]["reference"]}, timeout=30).json()
        assert r["result"] == "ALREADY_CHECKED_IN" and r["registration"]["branch_name"]

    def test_lowercase_reference_manual_entry(self, dataset, staff):
        # Manual reference typed in lowercase on a phone keyboard should still resolve (server upper()s the ref)
        r = requests.post(f"{API}/scan", headers=staff["scanner"], json={"token": "  " + dataset["a1"]["reference"].lower() + " "}, timeout=30).json()
        assert r["result"] == "ALREADY_CHECKED_IN", r

    def test_pending_and_invalid_ref(self, dataset, staff):
        r = requests.post(f"{API}/scan", headers=staff["scanner"], json={"token": dataset["p1"]["reference"]}, timeout=30).json()
        assert r["result"] == "NOT_APPROVED"
        r = requests.post(f"{API}/scan", headers=staff["scanner"], json={"token": "OLM-000000"}, timeout=30).json()
        assert r["result"] == "INVALID"


# --- Event day summary report
class TestEventDayReport:
    def test_shape(self, admin, dataset):
        s = _summary(admin)
        for k in ("generated_at", "totals", "by_branch", "by_batch", "by_branch_batch", "first_checkin", "last_checkin"):
            assert k in s, k
        for k in ("registered", "approved", "checked_in", "absent", "attendance_pct"):
            assert k in s["totals"], k
        assert s["first_checkin"] and s["last_checkin"] and s["first_checkin"] <= s["last_checkin"]

    def test_totals_delta(self, admin, dataset):
        b, t = dataset["before"], _summary(admin)["totals"]
        assert t["registered"] - b["registered"] == 4
        assert t["approved"] - b["approved"] == 3
        assert t["checked_in"] - b["checked_in"] == 1
        assert t["absent"] == max(t["approved"] - t["checked_in"], 0)
        exp = round(t["checked_in"] / t["approved"] * 100, 1) if t["approved"] else 0.0
        assert t["attendance_pct"] == exp

    def test_by_batch_exact(self, admin, dataset):
        row = next(x for x in _summary(admin)["by_batch"] if x["batch"] == BATCH)
        assert (row["registered"], row["approved"], row["checked_in"], row["absent"], row["attendance_pct"]) == (4, 3, 1, 2, 33.3)

    def test_by_branch_batch_exact(self, admin, dataset, branch_names):
        pairs = {(x["branch_name"], x["batch"]): x for x in _summary(admin)["by_branch_batch"]}
        k1 = pairs[(branch_names["br-1"], BATCH)]
        assert (k1["registered"], k1["approved"], k1["checked_in"], k1["absent"], k1["attendance_pct"]) == (3, 2, 1, 1, 50.0)
        k2 = pairs[(branch_names["br-2"], BATCH)]
        assert (k2["registered"], k2["approved"], k2["checked_in"], k2["absent"], k2["attendance_pct"]) == (1, 1, 0, 1, 0.0)

    def test_by_branch_consistent(self, admin, dataset):
        s = _summary(admin)
        assert sum(x["registered"] for x in s["by_branch"]) == s["totals"]["registered"]
        assert sum(x["checked_in"] for x in s["by_branch"]) == s["totals"]["checked_in"]
        assert sum(x["registered"] for x in s["by_batch"]) == s["totals"]["registered"]

    def test_coordinator_scoped(self, staff, dataset, branch_names):
        s = _summary(staff["coordinator"])
        assert {x["branch_name"] for x in s["by_branch"]} <= {branch_names["br-1"]}
        assert all(x["branch_name"] == branch_names["br-1"] for x in s["by_branch_batch"])
        row = next(x for x in s["by_batch"] if x["batch"] == BATCH)
        assert (row["registered"], row["approved"], row["checked_in"]) == (3, 2, 1)

    def test_scanner_forbidden(self, staff):
        assert requests.get(f"{API}/reports/event-day", headers=staff["scanner"], timeout=30).status_code == 403

    def test_unauthenticated(self):
        assert requests.get(f"{API}/reports/event-day", timeout=30).status_code in (401, 403)


# --- Event day CSV export
class TestEventDayCsv:
    def test_admin_csv(self, admin, dataset, branch_names):
        r = requests.get(f"{API}/export/event-day.csv", headers=admin, timeout=60)
        assert r.status_code == 200 and "text/csv" in r.headers["content-type"]
        rows = list(csv.reader(io.StringIO(r.text)))
        assert rows[0] == ["Branch", "Batch", "Registered", "Approved", "Checked In", "Absent", "Attendance %"]
        assert [branch_names["br-1"], BATCH, "3", "2", "1", "1", "50.0"] in rows
        assert rows[-1][0] == "ALL BRANCHES"

    def test_coordinator_without_export_403(self, staff):
        assert requests.get(f"{API}/export/event-day.csv", headers=staff["coordinator"], timeout=30).status_code == 403

    def test_scanner_403(self, staff):
        assert requests.get(f"{API}/export/event-day.csv", headers=staff["scanner"], timeout=30).status_code == 403

    def test_coordinator_with_export_scoped(self, admin, branch_names):
        email = f"test_coordexp_{uuid.uuid4().hex[:6]}@olam.delta"
        r = requests.post(f"{API}/staff", headers=admin, json={"email": email, "password": STAFF_PW, "name": "TEST coordexp",
                                                             "role": "coordinator", "branch_id": "br-1", "can_export": True}, timeout=30)
        assert r.status_code == 200, r.text
        h = _login(email, STAFF_PW)
        assert requests.post(f"{API}/auth/change-password", headers=h, json={"current_password": STAFF_PW, "new_password": STAFF_NEW_PW}, timeout=30).status_code == 200
        h = _login(email, STAFF_NEW_PW)
        c = requests.get(f"{API}/export/event-day.csv", headers=h, timeout=60)
        assert c.status_code == 200, c.text
        rows = list(csv.reader(io.StringIO(c.text)))[1:-1]
        assert rows and all(x[0] == branch_names["br-1"] for x in rows)
