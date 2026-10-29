# OLAM 3.0 iteration-11: persistent email queue (db.email_queue) - pass jobs on (bulk) approve, dedupe,
# /email/queue RBAC, reminders queue/409/status, resend re-queue, 429 -> pending (not failed).
# Uses only @resend.dev emails. Writes created ids to /tmp/iter11_state.json for cleanup.
import json
import os
import time
import uuid
import pytest
import requests
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")
BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
QA = {"email": "qa-admin@olam.delta", "password": "QaAdmin#2026x"}
DB = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
REAL_REFS = ["OLM-8932B1", "OLM-E9C76C", "OLM-72857B", "OLM-E04B9A", "OLM-7A2076"]
S = {}


def _save():
    json.dump({"regs": S.get("regs", []), "staff": S.get("staff", [])}, open("/tmp/iter11_state.json", "w"))


def _login(email, pw, **extra):
    return requests.post(f"{API}/auth/login", json={"email": email, "password": pw, **extra}, timeout=30)


def _h(tok):
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="module")
def admin_h():
    r = _login(QA["email"], QA["password"])
    assert r.status_code == 200, r.text
    return _h(r.json()["access_token"])


@pytest.fixture(scope="module")
def coord(admin_h):
    email = f"test_coord11_{uuid.uuid4().hex[:6]}@olam.delta"
    r = requests.post(f"{API}/staff", headers=admin_h, json={"email": email, "password": "TempStart#2026",
                      "name": "TEST Coord Eleven", "role": "coordinator", "branch_id": "br-1"}, timeout=30)
    assert r.status_code == 200, r.text
    S.setdefault("staff", []).append(email); _save()
    tok = _login(email, "TempStart#2026").json()["access_token"]
    r = requests.post(f"{API}/auth/change-password", headers=_h(tok),
                      json={"current_password": "TempStart#2026", "new_password": "CoordNew#2026x"}, timeout=30)
    assert r.status_code == 200, r.text
    r = _login(email, "CoordNew#2026x", sign_in_as="coordinator", branch_id="br-1")
    assert r.status_code == 200, r.text
    return _h(r.json()["access_token"])


def _register():
    tag = uuid.uuid4().hex[:6]
    r = requests.post(f"{API}/registrations", json={
        "full_name": f"TEST Iter11 {tag}", "mobile": "9" + str(uuid.uuid4().int)[:9],
        "email": f"delivered+olam11{tag}@resend.dev", "branch_id": "br-1", "batch": "A1", "batch_no": "7",
        "faculty_name": "TEST Faculty", "confirm": True, "privacy_accepted": True}, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_bulk_approve_creates_one_pass_job_each(coord):
    S["regs"] = [_register() for _ in range(3)]; _save()
    r = requests.post(f"{API}/registrations/bulk-approve", headers=coord, json={"ids": S["regs"]}, timeout=30)
    assert r.status_code == 200, r.text
    assert r.json()["approved"] == 3
    time.sleep(3)
    jobs = list(DB.email_queue.find({"registration_id": {"$in": S["regs"]}}, {"_id": 0}))
    print("JOBS:", [(j["kind"], j["key"], j["status"], j.get("attempts")) for j in jobs])
    assert len(jobs) == 3 and all(j["kind"] == "pass" for j in jobs)
    assert all(j["status"] in ("pending", "sending", "sent") for j in jobs)
    st = {x["pass_email_status"] for x in DB.registrations.find({"id": {"$in": S["regs"]}})}
    assert st <= {"queued", "sent"}, st


def test_no_duplicate_jobs_on_reapprove(coord):
    r = requests.post(f"{API}/registrations/bulk-approve", headers=coord, json={"ids": S["regs"]}, timeout=30)
    assert r.status_code == 200 and r.json()["approved"] == 0
    assert all("already approved" in s["reason"] for s in r.json()["skipped"])
    r = requests.post(f"{API}/registrations/{S['regs'][0]}/approve", headers=coord, timeout=30)
    assert r.status_code == 200, r.text
    time.sleep(2)
    assert DB.email_queue.count_documents({"registration_id": {"$in": S["regs"]}, "kind": "pass"}) == 3


def test_email_queue_rbac(admin_h, coord):
    r = requests.get(f"{API}/email/queue", headers=admin_h, timeout=30)
    assert r.status_code == 200, r.text
    assert set(r.json()) >= {"pending", "sent", "failed"}
    print("QUEUE:", r.json())
    assert requests.get(f"{API}/email/queue", headers=coord, timeout=30).status_code == 403


def test_reminders_queue_and_409(admin_h):
    cur = requests.get(f"{API}/settings", headers=admin_h, timeout=30).json()
    body = {"registration_open": cur.get("registration_open", True), "closed_message": cur.get("closed_message") or "Closed",
            "privacy_notice": cur.get("privacy_notice") or "Privacy", "event_date": "2026-03-15",
            "event_time_venue": "TEST venue", "auto_reminder": False}
    r = requests.put(f"{API}/settings", headers=admin_h, json=body, timeout=30)
    assert r.status_code == 200, r.text
    r = requests.post(f"{API}/reminders/send", headers=admin_h, timeout=30)
    assert r.status_code == 200, r.text
    n = r.json()["queued"]
    # never email the real students: drop their reminder jobs right away
    real_ids = [x["id"] for x in DB.registrations.find({"reference": {"$in": REAL_REFS}}, {"id": 1})]
    DB.email_queue.delete_many({"kind": "reminder", "registration_id": {"$in": real_ids}, "status": {"$ne": "sent"}})
    test_rem = DB.email_queue.count_documents({"kind": "reminder", "key": "2026-03-15", "registration_id": {"$in": S["regs"]}})
    print("REMINDERS queued:", n, "test-reg reminder jobs:", test_rem)
    assert n >= 3 and test_rem == 3
    r2 = requests.post(f"{API}/reminders/send", headers=admin_h, timeout=30)
    assert r2.status_code == 409, r2.text
    st = requests.get(f"{API}/reminders/status", headers=admin_h, timeout=30).json()
    print("REM STATUS:", st)
    for k in ("eligible", "already_sent", "pending", "queued", "failed", "sending", "email_backlog"):
        assert k in st
    assert st["queued"] >= 3 and st["sending"] is True


def test_resend_requeues_failed_job(admin_h):
    rid = S["regs"][1]
    DB.email_queue.update_one({"kind": "pass", "registration_id": rid}, {"$set": {"status": "failed"}})
    DB.registrations.update_one({"id": rid}, {"$set": {"pass_email_status": "failed"}})
    r = requests.post(f"{API}/registrations/{rid}/resend-email", headers=admin_h, timeout=30)
    assert r.status_code == 200, r.text
    time.sleep(2)
    j = DB.email_queue.find_one({"kind": "pass", "registration_id": rid})
    assert j["status"] in ("pending", "sending", "sent") and DB.email_queue.count_documents({"kind": "pass", "registration_id": rid}) == 1
    assert DB.registrations.find_one({"id": rid})["pass_email_status"] in ("queued", "sent")
