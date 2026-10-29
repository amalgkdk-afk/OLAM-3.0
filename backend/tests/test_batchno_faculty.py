# OLAM 3.0 iteration-6: mandatory Batch No. / Faculty Name on registrations, visibility (list/lookup/CSV), approve->scan regression
import os
import uuid
import csv
import io
import time
import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
QA = {"email": "qa-admin@olam.delta", "password": "QaAdmin#2026x"}
EMAIL = "delivered@resend.dev"


def _payload(**over):
    p = {"full_name": "TEST Iter6 Student", "mobile": "9" + str(uuid.uuid4().int)[:9],
         "email": EMAIL, "branch_id": "br-1", "batch": "TEST_Batch", "batch_no": "B-42",
         "faculty_name": "TEST Dr. Faculty", "confirm": True, "privacy_accepted": True}
    p.update(over)
    return p


def _post(url, **kw):
    r = requests.post(url, timeout=30, **kw)
    if r.status_code == 429:
        time.sleep(61)
        r = requests.post(url, timeout=30, **kw)
    return r


@pytest.fixture(scope="module")
def qa_h():
    r = requests.post(f"{API}/auth/login", json=QA, timeout=30)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="module")
def created():
    r = _post(f"{API}/registrations", json=_payload())
    assert r.status_code == 200, r.text
    return r.json()


# --- Validation: missing / whitespace-only required fields -> 422
class TestValidation:
    @pytest.mark.parametrize("field", ["batch_no", "faculty_name", "full_name", "mobile", "batch"])
    def test_missing_field_422(self, field):
        p = _payload()
        p.pop(field)
        r = requests.post(f"{API}/registrations", json=p, timeout=30)
        assert r.status_code == 422, f"{field}: {r.status_code} {r.text}"

    @pytest.mark.parametrize("field", ["batch_no", "faculty_name", "full_name", "mobile", "batch"])
    def test_whitespace_field_422(self, field):
        r = requests.post(f"{API}/registrations", json=_payload(**{field: "      "}), timeout=30)
        assert r.status_code == 422, f"{field}: {r.status_code} {r.text}"


# --- Create -> response contains new fields, stripped
class TestCreateAndVisibility:
    def test_create_has_fields(self, created):
        assert created["batch_no"] == "B-42"
        assert created["faculty_name"] == "TEST Dr. Faculty"
        assert created["status"] == "pending"
        assert created["reference"].startswith("OLM-")

    def test_strips_whitespace(self):
        r = _post(f"{API}/registrations", json=_payload(batch_no="  B7  ", faculty_name="  TEST Prof X  "))
        assert r.status_code == 200, r.text
        assert r.json()["batch_no"] == "B7" and r.json()["faculty_name"] == "TEST Prof X"

    def test_admin_list_includes_fields_and_old_records(self, qa_h, created):
        r = requests.get(f"{API}/registrations", headers=qa_h, timeout=30)
        assert r.status_code == 200, r.text
        regs = r.json()
        mine = [x for x in regs if x["id"] == created["id"]]
        assert mine and mine[0]["batch_no"] == "B-42" and mine[0]["faculty_name"] == "TEST Dr. Faculty"
        refs = {x["reference"] for x in regs}
        for old in ("OLM-8932B1", "OLM-E9C76C", "OLM-72857B", "OLM-E04B9A"):
            assert old in refs, f"old registration {old} missing from list"

    def test_get_by_id(self, qa_h, created):
        r = requests.get(f"{API}/registrations/{created['id']}", headers=qa_h, timeout=30)
        assert r.status_code == 200 and r.json()["batch_no"] == "B-42"

    def test_csv_columns(self, qa_h, created):
        r = requests.get(f"{API}/export/registrations.csv", headers=qa_h, timeout=60)
        assert r.status_code == 200, r.text
        rows = list(csv.reader(io.StringIO(r.text)))
        hdr = rows[0]
        assert "Batch No." in hdr and "Faculty Name" in hdr
        row = [x for x in rows if x and x[0] == created["reference"]][0]
        assert row[hdr.index("Batch No.")] == "B-42"
        assert row[hdr.index("Faculty Name")] == "TEST Dr. Faculty"

    def test_approve_lookup_scan(self, qa_h, created):
        a = requests.post(f"{API}/registrations/{created['id']}/approve", headers=qa_h, timeout=60)
        assert a.status_code == 200 and a.json()["status"] == "approved"
        lk = _post(f"{API}/registrations/lookup", json={"reference": created["reference"], "email": EMAIL})
        assert lk.status_code == 200, lk.text
        body = lk.json()
        reg = body.get("registration", body)
        assert reg.get("batch_no") == "B-42" and reg.get("faculty_name") == "TEST Dr. Faculty", body
        tok = body["pass_token"]
        s1 = requests.post(f"{API}/scan", json={"token": tok}, headers=qa_h, timeout=30).json()
        s2 = requests.post(f"{API}/scan", json={"token": tok}, headers=qa_h, timeout=30).json()
        assert s1["result"] == "VALID", s1
        assert s2["result"] == "ALREADY_CHECKED_IN", s2
