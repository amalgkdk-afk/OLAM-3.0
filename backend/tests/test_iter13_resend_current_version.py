# OLAM 3.0 iteration-13: resend-email must re-queue ONLY the current pass version's job.
# Flow: register -> approve (v1) -> mark v1 sent -> reject -> re-approve (v2) -> mark v2 sent -> resend
# Uses only @resend.dev emails. Cleans up its own registrations/passes/email_queue jobs.
import os
import time
import uuid
from datetime import datetime, timezone
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
STATE = {"rid": None}


@pytest.fixture(scope="module")
def admin_h():
    r = requests.post(f"{API}/auth/login", json=QA, timeout=30)
    assert r.status_code == 200, r.text
    yield {"Authorization": f"Bearer {r.json()['access_token']}"}
    rid = STATE["rid"]
    if rid:
        DB.registrations.delete_many({"id": rid})
        DB.passes.delete_many({"registration_id": rid})
        DB.email_queue.delete_many({"registration_id": rid})
        DB.audit_logs.delete_many({"registration_id": rid}) if "audit_logs" in DB.list_collection_names() else None


def _jobs(rid):
    return {j["key"]: j for j in DB.email_queue.find({"registration_id": rid, "kind": "pass"}, {"_id": 0})}


def _mark_sent(rid, key):
    DB.email_queue.update_one({"registration_id": rid, "kind": "pass", "key": key},
                              {"$set": {"status": "sent", "sent_at": datetime(2020, 1, 1, tzinfo=timezone.utc)}})


# Full reject/re-approve/resend flow
def test_resend_requeues_only_current_version(admin_h):
    tag = uuid.uuid4().hex[:6]
    r = requests.post(f"{API}/registrations", json={
        "full_name": f"TEST Iter13 {tag}", "mobile": "9" + str(uuid.uuid4().int)[:9],
        "email": f"delivered+olam13{tag}@resend.dev", "branch_id": "br-1", "batch": "A1", "batch_no": "7",
        "faculty_name": "TEST Faculty", "confirm": True, "privacy_accepted": True}, timeout=30)
    assert r.status_code == 200, r.text
    rid = STATE["rid"] = r.json()["id"]

    r = requests.post(f"{API}/registrations/{rid}/approve", headers=admin_h, timeout=30)
    assert r.status_code == 200 and r.json()["status"] == "approved", r.text
    time.sleep(1)
    _mark_sent(rid, "v1")
    assert DB.passes.find_one({"registration_id": rid})["version"] == 1

    r = requests.post(f"{API}/registrations/{rid}/reject", headers=admin_h, json={"reason": "TEST reject"}, timeout=30)
    assert r.status_code == 200 and r.json()["status"] == "rejected", r.text

    # Resend on rejected -> 400
    r = requests.post(f"{API}/registrations/{rid}/resend-email", headers=admin_h, timeout=30)
    assert r.status_code == 400, r.text

    r = requests.post(f"{API}/registrations/{rid}/approve", headers=admin_h, timeout=30)
    assert r.status_code == 200 and r.json()["status"] == "approved", r.text
    assert DB.passes.find_one({"registration_id": rid})["version"] == 2
    jobs = _jobs(rid)
    print("after re-approve:", {k: v["status"] for k, v in jobs.items()})
    assert set(jobs) == {"v1", "v2"}
    assert jobs["v1"]["status"] == "sent"
    time.sleep(1)
    _mark_sent(rid, "v2")

    r = requests.post(f"{API}/registrations/{rid}/resend-email", headers=admin_h, timeout=30)
    assert r.status_code == 200 and r.json() == {"ok": True}, r.text
    jobs = _jobs(rid)
    print("after resend:", {k: (v["status"], v.get("sent_at")) for k, v in jobs.items()})
    assert jobs["v1"]["status"] == "sent", "v1 must NOT be re-queued"
    assert jobs["v1"]["sent_at"].year == 2020
    v2 = jobs["v2"]
    assert v2["status"] in ("pending", "sending") or (v2["status"] == "sent" and v2["sent_at"].year > 2020), v2
    pending = [k for k, v in jobs.items() if v["status"] in ("pending", "sending")]
    assert pending in ([], ["v2"])
    reg = DB.registrations.find_one({"id": rid})
    assert reg["pass_email_status"] in ("queued", "sent")

    # Wait for the worker to deliver v2; v1 stays untouched
    end = time.time() + 60
    while time.time() < end and _jobs(rid)["v2"]["status"] != "sent":
        time.sleep(4)
    jobs = _jobs(rid)
    print("final:", {k: v["status"] for k, v in jobs.items()}, DB.registrations.find_one({"id": rid})["pass_email_status"])
    assert jobs["v1"]["status"] == "sent" and jobs["v1"]["sent_at"].year == 2020


# Auth guard
def test_resend_requires_auth():
    r = requests.post(f"{API}/registrations/nonexistent/resend-email", timeout=30)
    assert r.status_code in (401, 403)


def test_resend_404(admin_h):
    r = requests.post(f"{API}/registrations/does-not-exist/resend-email", headers=admin_h, timeout=30)
    assert r.status_code == 404
