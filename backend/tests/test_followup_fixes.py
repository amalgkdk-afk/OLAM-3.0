# OLAM 3.0 iteration-5 follow-up fixes: rate-limit spoof bypass (_client_ip) and per (email+IP) login lockout w/ per-email ceiling
# NOTE: restart backend after running (in-memory limits).
import os
import uuid
import random
import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
INTERNAL = "http://localhost:8001/api"  # only used to simulate distinct client IPs (no ingress in front)
QA = {"email": "qa-admin@olam.delta", "password": "QaAdmin#2026x"}
SCANNER_PW = "TestScan#2026x"


def _rand_ip():
    return ".".join(str(random.randint(1, 254)) for _ in range(4))


@pytest.fixture(scope="module")
def qa_h():
    r = requests.post(f"{API}/auth/login", json=QA, timeout=30)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="module")
def scanner(qa_h):
    email = f"test_scan_{uuid.uuid4().hex[:6]}@olam.delta"
    r = requests.post(f"{API}/staff", headers=qa_h, json={
        "email": email, "password": SCANNER_PW, "name": "TEST Lockout Scanner", "role": "scanner"}, timeout=30)
    assert r.status_code == 200, r.text
    yield {"email": email, "id": r.json()["id"]}
    requests.patch(f"{API}/staff/{r.json()['id']}", headers=qa_h, json={"active": False}, timeout=30)


# --- Rate limit bypass via spoofed headers (external URL) ---
class TestRateLimitSpoof:
    def test_lookup_rate_limit_not_bypassable(self):
        codes = []
        for i in range(17):
            h = {"X-Forwarded-For": f"{_rand_ip()}, {_rand_ip()}", "X-Forwarded-For": _rand_ip()}
            r = requests.post(f"{API}/registrations/lookup", headers=h,
                              json={"reference": "OLM-000000", "email": "nobody@example.com"}, timeout=30)
            codes.append(r.status_code)
        print("lookup codes:", codes)
        assert 429 in codes, f"No 429 with spoofed headers: {codes}"
        assert codes.index(429) <= 15, f"429 too late: {codes}"


# --- Login lockout per (email, IP) ---
class TestLoginLockout:
    def test_external_lockout_after_5(self, scanner):
        codes = []
        for _ in range(5):
            r = requests.post(f"{API}/auth/login", json={"email": scanner["email"], "password": "wrongPass123"}, timeout=30)
            codes.append(r.status_code)
        assert codes == [401] * 5, codes
        # correct password now locked from this IP
        r = requests.post(f"{API}/auth/login", json={"email": scanner["email"], "password": SCANNER_PW}, timeout=30)
        assert r.status_code == 429, r.text
        # spoofing headers must not unlock
        r = requests.post(f"{API}/auth/login", headers={"X-Real-IP": _rand_ip(), "X-Forwarded-For": _rand_ip()},
                          json={"email": scanner["email"], "password": SCANNER_PW}, timeout=30)
        assert r.status_code == 429, f"spoofed header unlocked: {r.status_code} {r.text}"

    def test_other_ip_not_locked(self, scanner):
        # Simulate a different real client IP directly against backend
        r = requests.post(f"{INTERNAL}/auth/login", headers={"X-Forwarded-For": "10.99.0.1"},
                          json={"email": scanner["email"], "password": SCANNER_PW}, timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["user"]["must_change_password"] is True

    def test_per_email_ceiling_30(self, scanner):
        # 30 fails from distinct IPs (4 each, below per-pair limit)
        total = 0  # other_ip_not_locked logs in successfully, which resets the per-email counter
        n = 0
        while total < 30:
            ip = f"10.98.{n}.1"
            for _ in range(4):
                if total >= 30:
                    break
                r = requests.post(f"{INTERNAL}/auth/login", headers={"X-Forwarded-For": ip},
                                  json={"email": scanner["email"], "password": "wrongPass123"}, timeout=30)
                assert r.status_code == 401, f"fail#{total+1} ip={ip}: {r.status_code}"
                total += 1
            n += 1
        r = requests.post(f"{INTERNAL}/auth/login", headers={"X-Forwarded-For": "10.97.0.1"},
                          json={"email": scanner["email"], "password": SCANNER_PW}, timeout=30)
        assert r.status_code == 429, f"ceiling not enforced: {r.status_code}"

    def test_other_email_unaffected(self):
        r = requests.post(f"{INTERNAL}/auth/login", headers={"X-Forwarded-For": "10.96.0.1"}, json=QA, timeout=30)
        assert r.status_code == 200, r.text
