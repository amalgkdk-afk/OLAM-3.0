# OLAM 3.0 iteration 2: branch editing (PATCH), attendance history log + scan attempts
import uuid
import requests
import pytest
from test_olam_api import API, _login, _register, _lookup, _scan, admin, staff  # noqa: F401

ORIGINAL = {"br-1": "KALOOR", "br-2": "ELAMAKKARA", "br-3": "MUVATTUPUZHA"}


def _patch(h, bid, name, active=True):
    return requests.patch(f"{API}/branches/{bid}", headers=h, json={"name": name, "active": active}, timeout=30)


@pytest.fixture(scope="module", autouse=True)
def restore_branches(admin):
    yield
    for bid, name in ORIGINAL.items():
        r = _patch(admin, bid, name, True)
        assert r.status_code == 200, r.text


# --- Branch editing
class TestBranchEdit:
    def test_rename_branch(self, admin):
        r = _patch(admin, "br-3", "TEST_MUVA_RENAMED")
        assert r.status_code == 200, r.text
        assert r.json()["name"] == "TEST_MUVA_RENAMED" and r.json()["active"] is True
        names = [b["name"] for b in requests.get(f"{API}/branches", headers=admin, timeout=30).json()]
        assert "TEST_MUVA_RENAMED" in names
        assert _patch(admin, "br-3", "MUVATTUPUZHA").status_code == 200

    def test_duplicate_name_409(self, admin):
        r = _patch(admin, "br-3", "KALOOR")
        assert r.status_code == 409, r.text

    def test_not_found_404(self, admin):
        assert _patch(admin, "br-nonexistent", "TEST_X").status_code == 404

    def test_coordinator_scanner_403(self, staff):
        assert _patch(staff["coordinator"], "br-1", "TEST_HACK").status_code == 403
        assert _patch(staff["scanner"], "br-1", "TEST_HACK").status_code == 403

    def test_inactive_hidden_and_rejected(self, admin):
        r = _patch(admin, "br-2", "ELAMAKKARA", False)
        assert r.status_code == 200 and r.json()["active"] is False
        pub = [b["id"] for b in requests.get(f"{API}/public/branches", timeout=30).json()]
        assert "br-2" not in pub
        r = requests.post(f"{API}/registrations", json={
            "full_name": "TEST Inactive", "mobile": "9" + str(uuid.uuid4().int)[:9],
            "email": "delivered@resend.dev", "branch_id": "br-2", "batch": "TEST_Batch", "batch_no": "B12", "faculty_name": "TEST Faculty", "confirm": True}, timeout=30)
        assert r.status_code == 400, r.text
        assert _patch(admin, "br-2", "ELAMAKKARA", True).status_code == 200
        pub = [b["id"] for b in requests.get(f"{API}/public/branches", timeout=30).json()]
        assert "br-2" in pub

    def test_empty_name_rejected(self, admin):
        r = _patch(admin, "br-1", "   ")
        assert r.status_code in (400, 422), f"blank name accepted: {r.status_code} {r.text}"


def _approved(admin, branch="br-1"):
    reg = _register(branch=branch)
    requests.post(f"{API}/registrations/{reg['id']}/approve", headers=admin, timeout=60)
    return reg, _lookup(reg["reference"]).json()["pass_token"]


# --- Attendance log
class TestAttendance:
    def test_checkin_and_attempts_logged(self, admin, staff):
        reg, tok = _approved(admin)
        before = requests.get(f"{API}/attendance", headers=admin, timeout=30).json()
        assert set(before.keys()) >= {"checkins", "attempts", "duplicate_count"}
        r = requests.post(f"{API}/scan", json={"token": tok, "station": "TEST-gate"}, headers=staff["scanner"], timeout=30).json()
        assert r["result"] == "VALID"
        assert _scan(staff["scanner"], tok)["result"] == "ALREADY_CHECKED_IN"
        assert _scan(staff["scanner"], "garbage-" + uuid.uuid4().hex)["result"] == "INVALID"
        pend = _register()
        assert _scan(staff["scanner"], pend["reference"])["result"] == "NOT_APPROVED"
        rej, old = _approved(admin)
        requests.post(f"{API}/registrations/{rej['id']}/reject", headers=admin, json={"reason": "TEST revoke"}, timeout=30)
        assert _scan(staff["scanner"], old)["result"] == "REVOKED"

        after = requests.get(f"{API}/attendance", headers=admin, timeout=30).json()
        ci = [c for c in after["checkins"] if c["reference"] == reg["reference"]]
        assert len(ci) == 1
        c = ci[0]
        assert c["station"] == "TEST-gate" and c["scanner_name"] == "TEST scanner"
        assert c["full_name"] == "TEST Student" and c["branch_name"] == "KALOOR" and c["checked_in_at"]
        assert after["duplicate_count"] == before["duplicate_count"] + 1
        assert len(after["attempts"]) == len(before["attempts"]) + 4
        res = {a["result"] for a in after["attempts"][:4]}
        assert res == {"ALREADY_CHECKED_IN", "INVALID", "NOT_APPROVED", "REVOKED"}, res
        for a in after["attempts"]:
            assert "_id" not in a

    def test_branch_filter_admin(self, admin):
        d = requests.get(f"{API}/attendance", params={"branch_id": "br-2"}, headers=admin, timeout=30).json()
        assert all(c["branch_name"] == "ELAMAKKARA" for c in d["checkins"])
        assert all(a.get("branch_id") == "br-2" for a in d["attempts"])

    def test_coordinator_scoped(self, staff):
        r = requests.get(f"{API}/attendance", params={"branch_id": "br-2"}, headers=staff["coordinator"], timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert all(c["branch_name"] == "KALOOR" for c in d["checkins"])
        assert all(a.get("branch_id") == "br-1" for a in d["attempts"])

    def test_scanner_forbidden(self, staff):
        assert requests.get(f"{API}/attendance", headers=staff["scanner"], timeout=30).status_code == 403
