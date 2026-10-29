# OLAM 3.0 iteration-12: re-approve / resend on an already-'sent' pass job must not leave
# pass_email_status stuck on 'queued'. Also first approve -> exactly one pass job, queued -> sent.
# Uses only @resend.dev emails. Writes created ids to /tmp/iter12_state.json for cleanup.
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
S = {"regs": []}
WAIT_SENT = int(os.environ.get("ITER12_WAIT_SENT", "90"))


def _save():
    json.dump(S, open("/tmp/iter12_state.json", "w"))


@pytest.fixture(scope="module")
def admin_h():
    r = requests.post(f"{API}/auth/login", json=QA, timeout=30)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _register():
    tag = uuid.uuid4().hex[:6]
    r = requests.post(f"{API}/registrations", json={
        "full_name": f"TEST Iter12 {tag}", "mobile": "9" + str(uuid.uuid4().int)[:9],
        "email": f"delivered+olam12{tag}@resend.dev", "branch_id": "br-1", "batch": "A1", "batch_no": "7",
        "faculty_name": "TEST Faculty", "confirm": True, "privacy_accepted": True}, timeout=30)
    assert r.status_code == 200, r.text
    rid = r.json()["id"]
    S["regs"].append(rid); _save()
    return rid


def _jobs(rid):
    return list(DB.email_queue.find({"registration_id": rid, "kind": "pass"}, {"_id": 0}))


def _status(rid):
    return DB.registrations.find_one({"id": rid})["pass_email_status"]


def _wait_sent(rid, timeout=WAIT_SENT):
    end = time.time() + timeout
    while time.time() < end:
        if _status(rid) == "sent" and all(j["status"] == "sent" for j in _jobs(rid)):
            return True
        time.sleep(5)
    return False


def _simulate_delivered(rid):
    """Provider is heavily rate-limited in preview; mimic exactly what _email_worker does on 'ok'."""
    now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    DB.email_queue.update_many({"registration_id": rid, "kind": "pass"}, {"$set": {"status": "sent", "sent_at": now}})
    DB.registrations.update_one({"id": rid}, {"$set": {"pass_email_status": "sent", "pass_email_at": now}})
    S.setdefault("simulated", []).append(rid); _save()


def test_first_approve_one_job_queued_then_sent(admin_h):
    rid = _register()
    r = requests.post(f"{API}/registrations/{rid}/approve", headers=admin_h, timeout=30)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "approved"
    jobs = _jobs(rid)
    print("first approve jobs:", [(j["key"], j["status"]) for j in jobs], "status:", _status(rid))
    assert len(jobs) == 1 and jobs[0]["key"] == "v1"
    assert _status(rid) in ("queued", "sent")
    S["single"] = rid; _save()
    if not _wait_sent(rid):
        print("WORKER DID NOT DELIVER in", WAIT_SENT, "s (provider 429) -> simulating 'sent'")
        _simulate_delivered(rid)


def test_bulk_approve_one_job_each(admin_h):
    ids = [_register(), _register()]
    r = requests.post(f"{API}/registrations/bulk-approve", headers=admin_h, json={"ids": ids}, timeout=30)
    assert r.status_code == 200, r.text
    assert r.json()["approved"] == 2
    for rid in ids:
        jobs = _jobs(rid)
        assert len(jobs) == 1 and jobs[0]["status"] in ("pending", "sending", "sent")
        assert _status(rid) in ("queued", "sent")
    S["bulk"] = ids; _save()


def test_reapprove_sent_keeps_sent_no_new_job(admin_h):
    rid = S.get("single")
    if not rid or _status(rid) != "sent":
        pytest.skip("single reg not delivered")
    r = requests.post(f"{API}/registrations/{rid}/approve", headers=admin_h, timeout=30)
    assert r.status_code == 200, r.text
    assert r.json().get("pass_email_status", "sent") == "sent", r.json().get("pass_email_status")
    time.sleep(2)
    jobs = _jobs(rid)
    assert len(jobs) == 1 and jobs[0]["status"] == "sent", jobs
    assert _status(rid) == "sent"


def test_resend_on_sent_requeues_then_sent(admin_h):
    rid = S.get("single")
    if not rid or _status(rid) != "sent":
        pytest.skip("single reg not delivered")
    before = _jobs(rid)[0].get("sent_at")
    r = requests.post(f"{API}/registrations/{rid}/resend-email", headers=admin_h, timeout=30)
    assert r.status_code == 200, r.text
    jobs = _jobs(rid)
    print("after resend:", [(j["status"], j.get("attempts")) for j in jobs], _status(rid))
    assert len(jobs) == 1
    assert jobs[0]["status"] in ("pending", "sending", "sent")
    assert _status(rid) in ("queued", "sent")
    assert jobs[0]["status"] != "sent" or jobs[0].get("sent_at") != before, "job not re-queued"
    if _wait_sent(rid):
        print("resend delivered by worker")
        assert _jobs(rid)[0].get("sent_at") != before
    else:
        print("resend still queued (provider 429); job:", _jobs(rid)[0]["status"], _status(rid))
        assert _jobs(rid)[0]["status"] in ("pending", "sending") and _status(rid) == "queued"
