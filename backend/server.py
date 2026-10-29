"""OLAM 3.0 - THE GRAND WEDDING  (FastAPI backend)

Features: role-based JWT auth, student registration, coordinator approval,
secure QR pass issuance + validation, duplicate-safe check-in, admin stats,
CSV export, audit log, Resend transactional email for pass delivery.
"""
from __future__ import annotations

import os
import re
import asyncio
import base64
import html as htmllib
import csv
import io
import hmac
import hashlib
import secrets as pysecrets
import logging
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Literal, Annotated

import bcrypt
import httpx
import jwt
from dotenv import load_dotenv
from fastapi import FastAPI, APIRouter, Depends, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, PlainTextResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, EmailStr, Field, field_validator
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

# ---------------------------------------------------------------------------
# Env + logging
# ---------------------------------------------------------------------------
ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("olam3")

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]
JWT_SECRET = os.environ["JWT_SECRET"]
JWT_ISSUER = os.getenv("JWT_ISSUER", "olam3-api")
ALLOWED_ALGS = ["HS256"]
APP_PUBLIC_URL = os.getenv("APP_PUBLIC_URL", "").rstrip("/")

EMAIL_BASE_URL = "https://integrations.emergentagent.com"
EMAIL_KEY = os.environ.get("EMERGENT_EMAIL_KEY", "")
EMAIL_FROM_NAME = os.environ.get("EMAIL_FROM_NAME", "OLAM 3.0 - Delta Academy")

STAFF_ROLES = {"super_admin", "coordinator", "scanner"}
Role = Literal["super_admin", "coordinator", "scanner", "student"]
RegStatus = Literal["pending", "approved", "rejected"]

client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]
bearer = HTTPBearer(auto_error=False)

app = FastAPI(title="OLAM 3.0 API")
api = APIRouter(prefix="/api")


@app.get("/health", include_in_schema=False)
@app.head("/health", include_in_schema=False)
async def health():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _hash_password(pw: str) -> str:
    raw = pw.encode()
    if len(raw) > 72:
        raise HTTPException(400, "Password too long")
    return bcrypt.hashpw(raw, bcrypt.gensalt(rounds=12)).decode()


def _verify_password(pw: str, stored: str) -> bool:
    raw = pw.encode()
    return len(raw) <= 72 and bcrypt.checkpw(raw, stored.encode())


def _normalize_phone(p: str) -> str:
    return re.sub(r"[^0-9+]", "", p or "")


def _make_token(user: dict, lifetime_min: int = 60 * 8) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": user["id"],
            "role": user["role"],
            "branch_id": user.get("branch_id"),
            "iat": now,
            "exp": now + timedelta(minutes=lifetime_min),
            "iss": JWT_ISSUER,
            "jti": pysecrets.token_urlsafe(16),
        },
        JWT_SECRET,
        algorithm="HS256",
    )


def _hash_pass_token(tok: str) -> str:
    return hmac.new(JWT_SECRET.encode(), tok.encode(), hashlib.sha256).hexdigest()


def _derive_pass_token(registration_id: str, version: int) -> str:
    """Pass token is derived (never stored): HMAC(secret, reg_id:version).
    Revocation/re-issue bumps `version`; DB stores only the hash."""
    mac = hmac.new(("pass-v1:" + JWT_SECRET).encode(), f"{registration_id}:{version}".encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(mac[:24]).decode().rstrip("=")


# --- simple in-memory rate limiting (single backend instance) --------------
_rl_hits: dict = {}
_login_fails: dict = {}


TRUSTED_PROXY_HOPS = int(os.getenv("TRUSTED_PROXY_HOPS", "2"))


def _client_ip(request: Request) -> str:
    # Our edge appends: <real client>, <CDN edge>, <load balancer>. Entries to the
    # left of the real client are caller-controlled, so count from the right.
    xff = [p.strip() for p in request.headers.get("x-forwarded-for", "").split(",") if p.strip()]
    if len(xff) > TRUSTED_PROXY_HOPS:
        return xff[-(TRUSTED_PROXY_HOPS + 1)]
    if xff:
        return xff[0]
    return request.client.host if request.client else "unknown"


def _rate_limit(bucket: str, key: str, limit: int, window_s: int):
    now = datetime.now(timezone.utc).timestamp()
    k = f"{bucket}:{key}"
    hits = [t for t in _rl_hits.get(k, []) if now - t < window_s]
    if len(hits) >= limit:
        raise HTTPException(429, "Too many attempts. Please wait a minute and try again.")
    hits.append(now)
    _rl_hits[k] = hits


def _password_ok(pw: str) -> bool:
    return len(pw) >= 10 and re.search(r"[A-Za-z]", pw) is not None and re.search(r"\d", pw) is not None


def _csv_safe(v) -> str:
    s = "" if v is None else str(v)
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s


def _dedupe_key(branch_id: str, mobile: str, full_name: str) -> str:
    digits = re.sub(r"\D", "", mobile or "")[-10:]
    name = re.sub(r"\s+", " ", (full_name or "").strip().lower())
    return f"{branch_id}|{digits}|{name}"


def _ref_code() -> str:
    # Public registration reference, e.g. OLM-7F3K2A
    return "OLM-" + pysecrets.token_hex(3).upper()


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, max_length=72)
    sign_in_as: Optional[Literal["super_admin", "coordinator", "scanner"]] = None
    branch_id: Optional[str] = None


class UserOut(BaseModel):
    id: str
    email: EmailStr
    role: Role
    name: Optional[str] = None
    branch_id: Optional[str] = None
    active: bool = True
    can_export: bool = False
    must_change_password: bool = False


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class BranchIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    active: bool = True

    @field_validator("name")
    @classmethod
    def _not_blank(cls, v):
        if not v.strip():
            raise ValueError("Name cannot be blank")
        return v.strip()


class BranchOut(BaseModel):
    id: str
    name: str
    active: bool
    created_at: datetime


class BatchIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)

    @field_validator("name")
    @classmethod
    def _not_blank(cls, v):
        if not v.strip():
            raise ValueError("Name cannot be blank")
        return v.strip()


class BatchOut(BaseModel):
    id: str
    name: str


class StaffCreateIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)
    name: str
    role: Literal["super_admin", "coordinator", "scanner"]
    branch_id: Optional[str] = None
    can_export: bool = False


class StaffUpdateIn(BaseModel):
    name: Optional[str] = None
    role: Optional[Literal["super_admin", "coordinator", "scanner"]] = None
    branch_id: Optional[str] = None
    active: Optional[bool] = None
    can_export: Optional[bool] = None
    password: Optional[str] = Field(default=None, min_length=8, max_length=72)


class RegistrationIn(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    mobile: str = Field(min_length=5, max_length=20)
    email: EmailStr
    branch_id: str = Field(min_length=1)
    batch: str = Field(min_length=1, max_length=80)
    batch_no: str = Field(min_length=1, max_length=30)
    faculty_name: str = Field(min_length=2, max_length=120)
    confirm: bool
    privacy_accepted: bool

    @field_validator("privacy_accepted")
    @classmethod
    def _must_accept(cls, v):
        if not v:
            raise ValueError("You must accept the privacy notice.")
        return v

    @field_validator("full_name", "mobile", "branch_id", "batch", "batch_no", "faculty_name")
    @classmethod
    def _required_text(cls, v, info):
        v = v.strip()
        mins = {"full_name": 2, "mobile": 5, "faculty_name": 2}
        if len(v) < mins.get(info.field_name, 1):
            raise ValueError("This field is required" if not v else "This field is too short")
        return v

    @field_validator("confirm")
    @classmethod
    def _must_confirm(cls, v):
        if not v:
            raise ValueError("You must confirm the information is accurate.")
        return v


class RegistrationOut(BaseModel):
    id: str
    reference: str
    full_name: str
    student_code: Optional[str] = None
    mobile: str
    email: EmailStr
    branch_id: str
    branch_name: Optional[str] = None
    batch_no: Optional[str] = None
    faculty_name: Optional[str] = None
    pass_email_status: Optional[str] = None
    batch: str
    status: RegStatus
    rejection_reason: Optional[str] = None
    created_at: datetime
    reviewed_by_name: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    checked_in: bool = False
    checked_in_at: Optional[datetime] = None


class RejectIn(BaseModel):
    reason: str = Field(min_length=3, max_length=400)


class PassLookupIn(BaseModel):
    reference: str
    email: EmailStr


class ScanIn(BaseModel):
    token: str = Field(min_length=4, max_length=200)
    station: Optional[str] = Field(default="station-1", max_length=50)


# ---------------------------------------------------------------------------
# Auth dependencies
# ---------------------------------------------------------------------------
async def current_user(
    request: Request,
    creds: Annotated[Optional[HTTPAuthorizationCredentials], Depends(bearer)],
) -> dict:
    if not creds or creds.scheme.lower() != "bearer":
        raise HTTPException(401, "Not authenticated")
    try:
        p = jwt.decode(
            creds.credentials,
            JWT_SECRET,
            algorithms=ALLOWED_ALGS,
            issuer=JWT_ISSUER,
            options={"require": ["sub", "role", "exp", "iss", "jti"]},
        )
    except Exception:
        raise HTTPException(401, "Invalid or expired token")
    user = await db.users.find_one({"id": p["sub"]}, {"_id": 0, "password_hash": 0})
    if not user or not user.get("active", True) or user.get("role") != p["role"]:
        raise HTTPException(401, "Invalid token")
    # Accounts with a default / admin-set password may only change it until they do.
    if user.get("must_change_password") and request.url.path not in ("/api/auth/me", "/api/auth/change-password"):
        raise HTTPException(403, "Password change required")
    return user


def require_roles(*roles: Role):
    async def dep(user=Depends(current_user)):
        if user["role"] not in roles:
            raise HTTPException(403, "Insufficient permissions")
        return user

    return dep


# ---------------------------------------------------------------------------
# Startup: indexes + seed
# ---------------------------------------------------------------------------
@app.on_event("startup")
async def startup():
    await db.users.create_index("email", unique=True)
    await db.users.create_index("id", unique=True)
    await db.branches.create_index("id", unique=True)
    await db.branches.create_index("name", unique=True)
    await db.batches.create_index("name", unique=True)
    await db.registrations.create_index("reference", unique=True)
    await db.registrations.create_index("id", unique=True)
    # Duplicate rule (no student ID): same branch + same mobile (last 10 digits) + same name.
    try:
        await db.registrations.drop_index("branch_id_1_student_code_1")
    except Exception:
        pass
    async for r in db.registrations.find({"dedupe_key": {"$exists": False}}, {"_id": 1, "branch_id": 1, "mobile": 1, "full_name": 1}):
        key = _dedupe_key(r["branch_id"], r.get("mobile", ""), r.get("full_name", ""))
        if not await db.registrations.find_one({"dedupe_key": key}):
            await db.registrations.update_one({"_id": r["_id"]}, {"$set": {"dedupe_key": key}})
    await db.registrations.create_index(
        "dedupe_key", unique=True, partialFilterExpression={"dedupe_key": {"$exists": True}}
    )
    await db.registrations.create_index("mobile")
    await db.passes.create_index("token_hash", unique=True)
    await db.passes.create_index("registration_id", unique=True)
    # Unique attendance per registration = duplicate-safe check-in.
    await db.attendance.create_index("registration_id", unique=True)
    await db.audit_logs.create_index("timestamp")

    # Seed default branches
    for i, name in enumerate(["KALOOR", "ELAMAKKARA", "MUVATTUPUZHA"], start=1):
        if not await db.branches.find_one({"id": f"br-{i}"}):
            await db.branches.insert_one(
                {
                    "id": f"br-{i}",
                    "name": name,
                    "active": True,
                    "created_at": datetime.now(timezone.utc),
                }
            )
    # Seed default batches only on a fresh database (admin manages them afterwards)
    if await db.batches.count_documents({}) == 0:
        for b in ["A1", "A2", "B1", "B2", "Preparation", "Passed out"]:
            await db.batches.insert_one({"id": "bt-" + pysecrets.token_hex(3), "name": b})

    # Seed super admin
    admin_email = os.environ.get("INITIAL_ADMIN_EMAIL", "").lower().strip()
    admin_pw = os.environ.get("INITIAL_ADMIN_PASSWORD", "")
    if admin_email and admin_pw and not await db.users.find_one({"email": admin_email}):
        await db.users.insert_one(
            {
                "id": "u-" + pysecrets.token_hex(6),
                "email": admin_email,
                "name": "Super Admin",
                "role": "super_admin",
                "branch_id": None,
                "password_hash": _hash_password(admin_pw),
                "active": True,
                "must_change_password": True,
                "created_at": datetime.now(timezone.utc),
            }
        )
        logger.info("Seeded super admin: %s", admin_email)
    # If the seeded admin still uses the bootstrap password, force a change.
    if admin_email and admin_pw:
        adm = await db.users.find_one({"email": admin_email})
        if adm and not adm.get("must_change_password") and _verify_password(admin_pw, adm["password_hash"]):
            await db.users.update_one({"id": adm["id"]}, {"$set": {"must_change_password": True}})

    # Migrate legacy passes: drop stored plain tokens, switch to derived tokens.
    async for p in db.passes.find({"$or": [{"plain_token": {"$exists": True}}, {"version": {"$exists": False}}]}):
        ver = int(p.get("version") or 1)
        await db.passes.update_one(
            {"_id": p["_id"]},
            {"$set": {"version": ver, "token_hash": _hash_pass_token(_derive_pass_token(p["registration_id"], ver))},
             "$unset": {"plain_token": ""}},
        )
    await db.scan_attempts.create_index("attempted_at")
    asyncio.create_task(_reminder_loop())
    # Email queue: unique job per (kind, registration, key); recover jobs interrupted by a restart.
    await db.email_queue.create_index([("kind", 1), ("registration_id", 1), ("key", 1)], unique=True)
    await db.email_queue.create_index([("status", 1), ("next_attempt_at", 1)])
    await db.email_queue.update_many({"status": "sending"}, {"$set": {"status": "pending"}})
    async for r in db.registrations.find({"status": "approved", "pass_email_status": {"$in": ["queued", "failed"]}}, {"_id": 0, "id": 1}):
        if not await db.email_queue.find_one({"kind": "pass", "registration_id": r["id"], "status": {"$in": ["pending", "sending"]}}):
            await _send_pass_email(r)
    _bg_tasks.add(asyncio.create_task(_email_worker()))  # start after indexes + recovery


_bg_tasks: set = set()
async def shutdown():
    client.close()


# ---------------------------------------------------------------------------
# AUDIT
# ---------------------------------------------------------------------------
async def audit(actor_id: Optional[str], action: str, target: Optional[str] = None, meta: Optional[dict] = None):
    await db.audit_logs.insert_one(
        {
            "id": "al-" + pysecrets.token_hex(6),
            "actor_id": actor_id,
            "action": action,
            "target_id": target,
            "timestamp": datetime.now(timezone.utc),
            "meta": meta or {},
        }
    )


# ---------------------------------------------------------------------------
# AUTH
# ---------------------------------------------------------------------------
@api.post("/auth/login", response_model=TokenOut)
async def login(body: LoginIn, request: Request):
    email = body.email.lower().strip()
    ip = _client_ip(request)
    _rate_limit("login-ip", ip, 20, 60)
    now = datetime.now(timezone.utc).timestamp()
    # Lock per (email, IP) so a stranger can't lock the real admin out from elsewhere;
    # a higher per-email ceiling still slows distributed guessing.
    pair_key = f"{email}|{ip}"
    fails = [t for t in _login_fails.get(pair_key, []) if now - t < 900]
    email_fails = [t for t in _login_fails.get(email, []) if now - t < 900]
    if len(fails) >= 5 or len(email_fails) >= 30:
        raise HTTPException(429, "Too many failed sign-ins. Try again in 15 minutes.")
    user = await db.users.find_one({"email": email})
    if not user or not user.get("active", True) or not _verify_password(body.password, user["password_hash"]):
        _login_fails[pair_key] = fails + [now]
        _login_fails[email] = email_fails + [now]
        await audit(user["id"] if user else None, "login.failed", None, {"email_domain": email.split("@")[-1]})
        raise HTTPException(401, "Invalid credentials")
    _login_fails.pop(pair_key, None)
    _login_fails.pop(email, None)
    if len(_login_fails) > 5000 or len(_rl_hits) > 20000:
        _login_fails.clear(); _rl_hits.clear()  # bound memory
    if user["role"] not in STAFF_ROLES:
        raise HTTPException(403, "Staff login only")
    # Password already verified: role / branch hints can't leak anything to outsiders.
    role_label = {"super_admin": "Admin", "coordinator": "Branch Coordinator", "scanner": "Gate Scanner"}
    if body.sign_in_as and body.sign_in_as != user["role"]:
        an = "an" if role_label[user["role"]][0] in "AEIOU" else "a"
        raise HTTPException(403, f"This account is {an} {role_label[user['role']]} account. Please choose '{role_label[user['role']]}' to sign in.")
    if user["role"] == "coordinator" and body.sign_in_as == "coordinator":
        own = await db.branches.find_one({"id": user.get("branch_id")}, {"_id": 0, "name": 1})
        own_name = own["name"] if own else "your branch"
        if body.branch_id != user.get("branch_id"):
            raise HTTPException(403, f"This coordinator account belongs to {own_name}. Please choose {own_name} to sign in.")
    token = _make_token(user)
    await audit(user["id"], "login")
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user["id"],
            "email": user["email"],
            "role": user["role"],
            "name": user.get("name"),
            "branch_id": user.get("branch_id"),
            "active": user.get("active", True),
            "can_export": user.get("can_export", False),
            "must_change_password": bool(user.get("must_change_password")),
        },
    }


@api.get("/auth/me", response_model=UserOut)
async def me(user=Depends(current_user)):
    return UserOut(**user)


class ChangePasswordIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=72)
    new_password: str = Field(min_length=10, max_length=72)


@api.post("/auth/change-password")
async def change_password(body: ChangePasswordIn, request: Request, user=Depends(current_user)):
    _rate_limit("chpw", user["id"], 10, 300)
    full = await db.users.find_one({"id": user["id"]})
    if not _verify_password(body.current_password, full["password_hash"]):
        raise HTTPException(400, "Current password is incorrect")
    if not _password_ok(body.new_password):
        raise HTTPException(400, "New password must be at least 10 characters with letters and numbers")
    if body.new_password == body.current_password or body.new_password == os.environ.get("INITIAL_ADMIN_PASSWORD"):
        raise HTTPException(400, "Choose a new password you have not used here before")
    await db.users.update_one(
        {"id": user["id"]},
        {"$set": {"password_hash": _hash_password(body.new_password), "must_change_password": False}},
    )
    await audit(user["id"], "password.change", user["id"])
    return {"ok": True}


# ---------------------------------------------------------------------------
# PUBLIC: branches + batches (needed by registration form)
# ---------------------------------------------------------------------------
@api.get("/public/branches", response_model=List[BranchOut])
async def public_branches():
    docs = await db.branches.find({"active": True}, {"_id": 0}).to_list(100)
    return [BranchOut(**d) for d in docs]


@api.get("/public/batches", response_model=List[BatchOut])
async def public_batches():
    docs = await db.batches.find({}, {"_id": 0}).to_list(100)
    return [BatchOut(**d) for d in docs]


# ---------------------------------------------------------------------------
# EVENT SETTINGS
# ---------------------------------------------------------------------------
DEFAULT_PRIVACY = (
    "Delta Academy collects your name, mobile number, email, branch, batch, batch number and faculty name "
    "only to verify you as a student and to manage entry to OLAM 3.0. Your details are visible only to the "
    "event admin and your branch coordinator, are never sold or shared, and will be deleted after the event."
)
DEFAULT_CLOSED = "Registration for OLAM 3.0 is currently closed. Please contact your branch coordinator."


class EventSettingsIn(BaseModel):
    registration_open: bool
    closed_message: str = Field(min_length=3, max_length=400)
    privacy_notice: str = Field(min_length=20, max_length=3000)
    event_date: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    event_time_venue: Optional[str] = Field(default=None, max_length=200)
    auto_reminder: bool = True

    @field_validator("event_date")
    @classmethod
    def _valid_date(cls, v):
        if v:
            datetime.strptime(v, "%Y-%m-%d")
        return v or None


async def _get_settings() -> dict:
    s = await db.settings.find_one({"id": "event"}, {"_id": 0})
    return {
        "registration_open": True if not s else bool(s.get("registration_open", True)),
        "closed_message": (s or {}).get("closed_message") or DEFAULT_CLOSED,
        "privacy_notice": (s or {}).get("privacy_notice") or DEFAULT_PRIVACY,
        "updated_at": (s or {}).get("updated_at"),
        "updated_by_name": (s or {}).get("updated_by_name"),
        "event_date": (s or {}).get("event_date"),
        "event_time_venue": (s or {}).get("event_time_venue"),
        "auto_reminder": True if not s else bool(s.get("auto_reminder", True)),
        "auto_reminder_done_for": (s or {}).get("auto_reminder_done_for"),
    }


@api.get("/public/settings")
async def public_settings():
    s = await _get_settings()
    return {k: s[k] for k in ("registration_open", "closed_message", "privacy_notice")}


@api.get("/settings")
async def get_settings(user=Depends(require_roles("super_admin"))):
    return await _get_settings()


@api.put("/settings")
async def update_settings(body: EventSettingsIn, user=Depends(require_roles("super_admin"))):
    doc = {
        "id": "event",
        "registration_open": body.registration_open,
        "closed_message": body.closed_message.strip(),
        "privacy_notice": body.privacy_notice.strip(),
        "event_date": body.event_date,
        "event_time_venue": (body.event_time_venue or "").strip() or None,
        "auto_reminder": body.auto_reminder,
        "updated_at": datetime.now(timezone.utc),
        "updated_by_name": user.get("name") or user["email"],
    }
    await db.settings.update_one({"id": "event"}, {"$set": doc}, upsert=True)
    await audit(user["id"], "settings.update", "event", {"registration_open": body.registration_open})
    return await _get_settings()


async def _reminder_counts() -> dict:
    s = await _get_settings()
    key = s.get("event_date") or datetime.now(timezone.utc).date().isoformat()
    checked = {a["registration_id"] for a in await db.attendance.find({}, {"_id": 0, "registration_id": 1}).to_list(10000)}
    approved = await db.registrations.find({"status": "approved"}, {"_id": 0, "id": 1, "reminder_sent_for": 1}).to_list(10000)
    eligible = [r for r in approved if r["id"] not in checked]
    pending = [r for r in eligible if r.get("reminder_sent_for") != key]
    queued = await db.email_queue.count_documents({"kind": "reminder", "key": key, "status": {"$in": ["pending", "sending"]}})
    failed = await db.email_queue.count_documents({"kind": "reminder", "key": key, "status": "failed"})
    backlog = await db.email_queue.count_documents({"status": {"$in": ["pending", "sending"]}})
    return {"eligible": len(eligible), "already_sent": len(eligible) - len(pending), "pending": len(pending),
            "queued": queued, "failed": failed, "sending": queued > 0, "email_backlog": backlog}


async def _queue_reminders(tomorrow: bool) -> int:
    s = await _get_settings()
    key = s.get("event_date") or datetime.now(timezone.utc).date().isoformat()
    checked = {a["registration_id"] for a in await db.attendance.find({}, {"_id": 0, "registration_id": 1}).to_list(10000)}
    n = 0
    async for reg in db.registrations.find({"status": "approved", "reminder_sent_for": {"$ne": key}}, {"_id": 0, "id": 1}):
        if reg["id"] not in checked and await _enqueue_email("reminder", reg["id"], key, {"tomorrow": tomorrow}):
            n += 1
    return n


@api.get("/reminders/status")
async def reminder_status(user=Depends(require_roles("super_admin"))):
    return await _reminder_counts()


@api.post("/reminders/send")
async def reminder_send(user=Depends(require_roles("super_admin"))):
    if (await _reminder_counts())["queued"] > 0:
        raise HTTPException(409, "Reminders are already being sent. Please wait.")
    n = await _queue_reminders(tomorrow=False)
    await audit(user["id"], "reminders.send", None, {"queued": n})
    return {"queued": n}


# ---------------------------------------------------------------------------
# REGISTRATION (public submit, status, pass retrieval)
# ---------------------------------------------------------------------------
async def _send_once(to: str, subject: str, html: str) -> str:
    """One delivery attempt. Returns 'ok', 'retry' (provider busy / transient) or 'fail'."""
    if not EMAIL_KEY:
        return "fail"
    try:
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.post(f"{EMAIL_BASE_URL}/api/v1/email/send", headers={"X-Email-Key": EMAIL_KEY},
                             json={"to": [to], "subject": subject, "html": html, "from_name": EMAIL_FROM_NAME})
        if r.status_code < 300:
            return "ok"
        if r.status_code == 429 or r.status_code >= 500:
            return "retry"
        logger.warning("Email rejected: %s %s", r.status_code, r.text[:200])
        return "fail"
    except Exception as e:
        logger.warning("Email send error: %s", e)
        return "retry"


async def _enqueue_email(kind: str, registration_id: str, key: str, extra: Optional[dict] = None) -> bool:
    """Persistent, de-duplicated email job. Re-queues a previously failed job. Returns True if queued."""
    now = datetime.now(timezone.utc)
    r = await db.email_queue.update_one(
        {"kind": kind, "registration_id": registration_id, "key": key, "status": "failed"},
        {"$set": {"status": "pending", "attempts": 0, "next_attempt_at": now}},
    )
    if r.modified_count:
        return True
    try:
        await db.email_queue.insert_one({
            "id": "eq-" + pysecrets.token_hex(6), "kind": kind, "registration_id": registration_id, "key": key,
            "status": "pending", "attempts": 0, "next_attempt_at": now, "created_at": now, **(extra or {}),
        })
        return True
    except DuplicateKeyError:
        return False


MAX_EMAIL_ATTEMPTS = 240  # ~4h+ of retries at >=60s spacing


async def _email_worker():
    """Single worker: survives restarts (jobs live in MongoDB), pauses when the provider rate-limits."""
    while True:
        try:
            now = datetime.now(timezone.utc)
            job = await db.email_queue.find_one_and_update(
                {"status": "pending", "next_attempt_at": {"$lte": now}},
                {"$set": {"status": "sending"}}, sort=[("created_at", 1)], return_document=ReturnDocument.AFTER,
            )
            if not job:
                await asyncio.sleep(5)
                continue
            reg = await db.registrations.find_one({"id": job["registration_id"]}, {"_id": 0})
            skip = not reg or reg["status"] != "approved" or not APP_PUBLIC_URL
            if not skip and job["kind"] == "reminder" and await db.attendance.find_one({"registration_id": reg["id"]}):
                skip = True
            if skip:
                await db.email_queue.update_one({"_id": job["_id"]}, {"$set": {"status": "skipped"}})
                continue
            if job["kind"] == "pass":
                subject, html = "Your OLAM 3.0 pass is ready", _pass_html(reg)
            else:
                s = await _get_settings()
                tom = bool(job.get("tomorrow"))
                subject = "OLAM 3.0 is tomorrow – your pass" if tom else "Reminder: your OLAM 3.0 pass"
                html = _reminder_html(reg, s, tom)
            res = await _send_once(reg["email"], subject, html)
            if res == "ok":
                await db.email_queue.update_one({"_id": job["_id"]}, {"$set": {"status": "sent", "sent_at": now}})
                if job["kind"] == "pass":
                    await db.registrations.update_one({"id": reg["id"]}, {"$set": {"pass_email_status": "sent", "pass_email_at": now}})
                else:
                    await db.registrations.update_one({"id": reg["id"]}, {"$set": {"reminder_sent_for": job["key"], "reminder_sent_at": now}})
                await asyncio.sleep(1)
            elif res == "retry" and job.get("attempts", 0) + 1 < MAX_EMAIL_ATTEMPTS:
                await db.email_queue.update_one(
                    {"_id": job["_id"]},
                    {"$set": {"status": "pending", "next_attempt_at": now + timedelta(seconds=60)}, "$inc": {"attempts": 1}},
                )
                logger.info("Email provider busy; pausing 60s (job %s attempt %s)", job["id"], job.get("attempts", 0) + 1)
                await asyncio.sleep(60)
            else:
                await db.email_queue.update_one({"_id": job["_id"]}, {"$set": {"status": "failed"}})
                if job["kind"] == "pass":
                    await db.registrations.update_one({"id": reg["id"]}, {"$set": {"pass_email_status": "failed"}})
        except Exception as e:
            logger.warning("email worker error: %s", e)
            await asyncio.sleep(5)


def _reminder_html(reg: dict, settings: dict, tomorrow: bool) -> str:
    e = htmllib.escape
    first = e((reg["full_name"].split() or ["Guest"])[0])
    link = f"{APP_PUBLIC_URL}/my-pass?ref={reg['reference']}"
    when = e(settings.get("event_date") or "")
    extra = e(settings.get("event_time_venue") or "")
    lead = "OLAM 3.0 is <strong>tomorrow</strong>!" if tomorrow else "A friendly reminder about OLAM 3.0."
    details = "".join(f'<p style="font-size:14px;color:#0B192C;margin:4px 0">{x}</p>' for x in [when, extra] if x)
    return (
        f'<table role="presentation" width="100%" style="background:#FDFBF7"><tr><td align="center" style="padding:32px 16px;font-family:Arial,sans-serif;color:#0B192C">'
        f'<table role="presentation" width="100%" style="max-width:540px;background:#FFFFFF;border:1px solid #E5E0D8;border-radius:16px;padding:28px"><tr><td style="text-align:center">'
        f'<p style="font-size:12px;letter-spacing:4px;color:#8A6A12;margin:0">DELTA ACADEMY PRESENTS</p>'
        f'<h1 style="font-family:Georgia,serif;font-size:28px;margin:6px 0 2px 0">OLAM 3.0</h1>'
        f'<p style="font-size:12px;letter-spacing:3px;color:#5C6B82;margin:0 0 20px 0">THE GRAND WEDDING</p>'
        f'<p style="font-size:16px;margin:0 0 8px 0">Namaste {first},</p>'
        f'<p style="font-size:14px;color:#374151;line-height:22px;margin:0 0 12px 0">{lead} Keep your QR pass ready on your phone or printed.</p>'
        f'{details}'
        f'<a href="{link}" style="display:inline-block;margin-top:16px;background:#D4AF37;color:#0B192C;text-decoration:none;padding:14px 28px;border-radius:999px;font-weight:bold;font-size:14px">Open My Pass</a>'
        f'<p style="font-size:12px;color:#5C6B82;margin:20px 0 0 0">Reference: <strong>{e(reg["reference"])}</strong> &middot; open the link and confirm your email</p>'
        f'</td></tr></table></td></tr></table>'
    )


async def _reminder_loop():
    from zoneinfo import ZoneInfo
    while True:
        try:
            s = await _get_settings()
            if s.get("auto_reminder") and s.get("event_date"):
                today = datetime.now(ZoneInfo("Asia/Kolkata")).date()
                event_day = datetime.strptime(s["event_date"], "%Y-%m-%d").date()
                if (event_day - today).days == 1 and s.get("auto_reminder_done_for") != s["event_date"]:
                    n = await _queue_reminders(tomorrow=True)  # persistent queue retries on its own
                    await db.settings.update_one({"id": "event"}, {"$set": {"auto_reminder_done_for": s["event_date"]}})
                    logger.info("Auto reminders queued: %s", n)
        except Exception as e:
            logger.warning("reminder loop error: %s", e)
        await asyncio.sleep(900)


async def _send_pass_email(reg: dict, pass_token: str = "") -> None:
    """Queue the 'your pass is ready' email (delivered by the persistent email worker)."""
    p = await db.passes.find_one({"registration_id": reg["id"]}, {"_id": 0, "version": 1})
    key = f"v{(p or {}).get('version', 1)}"
    if await _enqueue_email("pass", reg["id"], key):
        await db.registrations.update_one({"id": reg["id"]}, {"$set": {"pass_email_status": "queued"}})
    else:
        job = await db.email_queue.find_one({"kind": "pass", "registration_id": reg["id"], "key": key}, {"_id": 0, "status": 1})
        st = {"sent": "sent", "failed": "failed", "skipped": "failed"}.get((job or {}).get("status"), "queued")
        await db.registrations.update_one({"id": reg["id"]}, {"$set": {"pass_email_status": st}})


def _pass_html(reg: dict) -> str:
    # Link carries only the public reference; the student confirms their email to open the pass.
    link = f"{APP_PUBLIC_URL}/my-pass?ref={reg['reference']}"
    first_name = htmllib.escape((reg["full_name"].split() or ["Guest"])[0])
    return (
        f'<table role="presentation" width="100%" style="background:#FDFBF7;padding:0;margin:0">'
        f'<tr><td align="center" style="padding:32px 16px;font-family:Arial,sans-serif;color:#0B192C">'
        f'<table role="presentation" width="100%" style="max-width:540px;background:#FFFFFF;border:1px solid #E5E0D8;border-radius:16px;padding:28px">'
        f'<tr><td style="text-align:center">'
        f'<p style="font-size:12px;letter-spacing:4px;color:#D4AF37;margin:0">DELTA ACADEMY PRESENTS</p>'
        f'<h1 style="font-family:Georgia,serif;font-size:28px;margin:6px 0 2px 0;color:#0B192C">OLAM 3.0</h1>'
        f'<p style="font-size:12px;letter-spacing:3px;color:#5C6B82;margin:0 0 20px 0">THE GRAND WEDDING</p>'
        f'<p style="font-size:16px;margin:0 0 8px 0">Namaste {first_name},</p>'
        f'<p style="font-size:14px;color:#374151;line-height:22px;margin:0 0 20px 0">Your registration has been <strong style="color:#10B981">approved</strong>. Your digital QR pass is ready. Please present it at the entrance on event day.</p>'
        f'<a href="{link}" style="display:inline-block;background:#D4AF37;color:#0B192C;text-decoration:none;padding:14px 28px;border-radius:999px;font-weight:bold;font-size:14px">View My Digital Pass</a>'
        f'<p style="font-size:12px;color:#5C6B82;margin:24px 0 0 0">Reference: <strong>{reg["reference"]}</strong></p>'
        f'<p style="font-size:11px;color:#9CA3AF;margin:20px 0 0 0">Sent by {EMAIL_FROM_NAME}. We never ask for your password by email.</p>'
        f"</td></tr></table></td></tr></table>"
    )


@api.post("/registrations/{rid}/resend-email")
async def resend_pass_email(rid: str, user=Depends(require_roles("super_admin", "coordinator"))):
    reg = await db.registrations.find_one({"id": rid}, {"_id": 0})
    if not reg:
        raise HTTPException(404, "Not found")
    if user["role"] == "coordinator" and reg["branch_id"] != user.get("branch_id"):
        raise HTTPException(403, "Not your branch")
    if reg["status"] != "approved":
        raise HTTPException(400, "Only approved students have a pass to email")
    # Explicit resend: re-deliver only the CURRENT pass version's email (even if already sent).
    p = await db.passes.find_one({"registration_id": rid}, {"_id": 0, "version": 1})
    await db.email_queue.update_many(
        {"kind": "pass", "registration_id": rid, "key": f"v{(p or {}).get('version', 1)}", "status": {"$in": ["sent", "failed", "skipped"]}},
        {"$set": {"status": "pending", "attempts": 0, "next_attempt_at": datetime.now(timezone.utc)}},
    )
    await _send_pass_email(reg)
    return {"ok": True}


@api.post("/registrations", response_model=RegistrationOut)
async def submit_registration(body: RegistrationIn, request: Request):
    settings = await _get_settings()
    if not settings["registration_open"]:
        raise HTTPException(403, settings["closed_message"])
    branch = await db.branches.find_one({"id": body.branch_id, "active": True})
    if not branch:
        raise HTTPException(400, "Invalid branch")
    _rate_limit("register-ip", _client_ip(request), 10, 60)
    phone = _normalize_phone(body.mobile)
    now = datetime.now(timezone.utc)
    reg = {
        "id": "reg-" + pysecrets.token_hex(6),
        "reference": _ref_code(),
        "full_name": body.full_name.strip(),
        "mobile": phone,
        "dedupe_key": _dedupe_key(body.branch_id, phone, body.full_name),
        "email": body.email.lower().strip(),
        "branch_id": body.branch_id,
        "batch": body.batch,
        "batch_no": body.batch_no,
        "faculty_name": body.faculty_name,
        "privacy_accepted_at": now,
        "status": "pending",
        "rejection_reason": None,
        "created_at": now,
        "updated_at": now,
        "reviewed_by": None,
        "reviewed_by_name": None,
        "reviewed_at": None,
    }
    try:
        await db.registrations.insert_one(reg)
    except DuplicateKeyError:
        raise HTTPException(409, "You have already registered with this name and mobile number for this branch. Use 'Retrieve my pass' to check your status.")
    await audit(None, "registration.submit", reg["id"], {"reference": reg["reference"]})
    return RegistrationOut(**reg, branch_name=branch["name"], checked_in=False)


async def _enrich_registration(reg: dict) -> dict:
    branch = await db.branches.find_one({"id": reg["branch_id"]}, {"_id": 0, "name": 1})
    att = await db.attendance.find_one({"registration_id": reg["id"]}, {"_id": 0})
    return {
        **reg,
        "branch_name": branch["name"] if branch else None,
        "checked_in": bool(att),
        "checked_in_at": att["checked_in_at"] if att else None,
    }


@api.post("/registrations/lookup")
async def lookup_registration(body: PassLookupIn, request: Request):
    """Public retrieval. Requires reference AND matching email, returns status
    and (if approved) the derived pass token (shown only to the student)."""
    _rate_limit("lookup-ip", _client_ip(request), 15, 60)
    ref = body.reference.strip().upper()
    reg = await db.registrations.find_one({"reference": ref}, {"_id": 0})
    if not reg or reg["email"].lower() != body.email.lower().strip():
        raise HTTPException(404, "No matching registration found")
    enriched = await _enrich_registration(reg)
    out = {
        "registration": RegistrationOut(**enriched).model_dump(),
        "pass_token": None,
    }
    if reg["status"] == "approved":
        pass_doc = await db.passes.find_one({"registration_id": reg["id"], "active": True}, {"_id": 0})
        if pass_doc:
            out["pass_token"] = _derive_pass_token(reg["id"], int(pass_doc.get("version") or 1))
    return out


class PassVerifyIn(BaseModel):
    token: str = Field(min_length=10, max_length=200)


@api.post("/pass/verify")
async def pass_verify_public(body: PassVerifyIn, request: Request):
    """Student app uses this to show the live pass detail without authentication,
    using the token itself as proof-of-possession (sent in the body, not the URL). Does NOT check in."""
    _rate_limit("verify-ip", _client_ip(request), 30, 60)
    th = _hash_pass_token(body.token)
    p = await db.passes.find_one({"token_hash": th, "active": True}, {"_id": 0})
    if not p:
        raise HTTPException(404, "Pass not found or revoked")
    reg = await db.registrations.find_one({"id": p["registration_id"]}, {"_id": 0})
    if not reg or reg["status"] != "approved":
        raise HTTPException(403, "Pass not currently valid")
    enriched = await _enrich_registration(reg)
    return {"registration": RegistrationOut(**enriched).model_dump()}


# ---------------------------------------------------------------------------
# COORDINATOR / ADMIN: list + approve + reject + revoke
# ---------------------------------------------------------------------------
def _branch_filter(user: dict) -> dict:
    if user["role"] == "coordinator":
        if not user.get("branch_id"):
            raise HTTPException(403, "Coordinator not assigned a branch")
        return {"branch_id": user["branch_id"]}
    return {}


@api.get("/registrations", response_model=List[RegistrationOut])
async def list_registrations(
    status_: Optional[RegStatus] = None,
    q: Optional[str] = None,
    branch_id: Optional[str] = None,
    user=Depends(require_roles("super_admin", "coordinator")),
):
    filt: dict = {}
    if user["role"] == "coordinator":
        filt["branch_id"] = user["branch_id"]
    elif branch_id:
        filt["branch_id"] = branch_id
    if status_:
        filt["status"] = status_
    if q:
        rx = {"$regex": re.escape(q), "$options": "i"}
        filt["$or"] = [
            {"full_name": rx},
            {"faculty_name": rx},
            {"batch_no": rx},
            {"mobile": rx},
            {"email": rx},
            {"reference": rx},
            {"batch": rx},
        ]
    docs = await db.registrations.find(filt, {"_id": 0}).sort("created_at", -1).to_list(2000)
    out = []
    for d in docs:
        out.append(RegistrationOut(**(await _enrich_registration(d))))
    return out


@api.get("/registrations/{rid}", response_model=RegistrationOut)
async def get_registration(rid: str, user=Depends(require_roles("super_admin", "coordinator"))):
    reg = await db.registrations.find_one({"id": rid}, {"_id": 0})
    if not reg:
        raise HTTPException(404, "Not found")
    if user["role"] == "coordinator" and reg["branch_id"] != user.get("branch_id"):
        raise HTTPException(403, "Not your branch")
    return RegistrationOut(**(await _enrich_registration(reg)))


async def _issue_pass(reg: dict) -> str:
    """Create or re-issue a pass. Each (re)issue bumps the version so any older
    QR stops working. Only the token hash is stored."""
    existing = await db.passes.find_one({"registration_id": reg["id"]})
    now = datetime.now(timezone.utc)
    if existing and existing.get("active"):
        # Already valid: keep the same pass (approve is idempotent).
        return _derive_pass_token(reg["id"], int(existing.get("version") or 1))
    version = int(existing.get("version") or 1) + 1 if existing else 1
    token = _derive_pass_token(reg["id"], version)
    th = _hash_pass_token(token)
    if existing:
        await db.passes.update_one(
            {"registration_id": reg["id"]},
            {"$set": {"token_hash": th, "version": version, "active": True, "revoked_at": None, "issued_at": now},
             "$unset": {"plain_token": ""}},
        )
    else:
        await db.passes.insert_one(
            {
                "id": "ps-" + pysecrets.token_hex(6),
                "registration_id": reg["id"],
                "token_hash": th,
                "version": version,
                "active": True,
                "issued_at": now,
                "revoked_at": None,
            }
        )
    return token


@api.post("/registrations/{rid}/approve", response_model=RegistrationOut)
async def approve_registration(rid: str, user=Depends(require_roles("super_admin", "coordinator"))):
    reg = await db.registrations.find_one({"id": rid}, {"_id": 0})
    if not reg:
        raise HTTPException(404, "Not found")
    if user["role"] == "coordinator" and reg["branch_id"] != user.get("branch_id"):
        raise HTTPException(403, "Not your branch")
    reg2, plain = await _approve_one(reg, user)
    await _send_pass_email(reg2, plain)
    reg2 = await db.registrations.find_one({"id": rid}, {"_id": 0})
    return RegistrationOut(**(await _enrich_registration(reg2)))


class BulkApproveIn(BaseModel):
    ids: List[str] = Field(min_length=1, max_length=200)


async def _send_many(regs: list):
    for r in regs:
        await _send_pass_email(r)


@api.get("/email/queue")
async def email_queue_status(user=Depends(require_roles("super_admin"))):
    agg = {d["_id"]: d["n"] async for d in db.email_queue.aggregate([{"$group": {"_id": "$status", "n": {"$sum": 1}}}])}
    return {"pending": agg.get("pending", 0) + agg.get("sending", 0), "sent": agg.get("sent", 0), "failed": agg.get("failed", 0)}


@api.post("/registrations/bulk-approve")
async def bulk_approve(body: BulkApproveIn, user=Depends(require_roles("super_admin", "coordinator"))):
    approved, skipped, emails = [], [], []
    for rid in dict.fromkeys(body.ids):
        reg = await db.registrations.find_one({"id": rid}, {"_id": 0})
        if not reg:
            skipped.append({"id": rid, "reason": "not found"}); continue
        if user["role"] == "coordinator" and reg["branch_id"] != user.get("branch_id"):
            skipped.append({"id": rid, "reason": "not your branch"}); continue
        if reg["status"] != "pending":
            skipped.append({"id": rid, "reason": f"already {reg['status']}"}); continue
        reg2, _ = await _approve_one(reg, user)
        approved.append(rid); emails.append(reg2)
    await _send_many(emails)
    await audit(user["id"], "registration.bulk_approve", None, {"count": len(approved)})
    return {"approved": len(approved), "skipped": skipped}


async def _approve_one(reg: dict, user: dict):
    rid = reg["id"]
    now = datetime.now(timezone.utc)
    await db.registrations.update_one(
        {"id": rid},
        {
            "$set": {
                "status": "approved",
                "rejection_reason": None,
                "reviewed_by": user["id"],
                "reviewed_by_name": user.get("name") or user["email"],
                "reviewed_at": now,
                "updated_at": now,
            }
        },
    )
    plain = await _issue_pass(reg)
    reg2 = await db.registrations.find_one({"id": rid}, {"_id": 0})
    await audit(user["id"], "registration.approve", rid)
    return reg2, plain


@api.post("/registrations/{rid}/reject", response_model=RegistrationOut)
async def reject_registration(rid: str, body: RejectIn, user=Depends(require_roles("super_admin", "coordinator"))):
    reg = await db.registrations.find_one({"id": rid}, {"_id": 0})
    if not reg:
        raise HTTPException(404, "Not found")
    if user["role"] == "coordinator" and reg["branch_id"] != user.get("branch_id"):
        raise HTTPException(403, "Not your branch")
    now = datetime.now(timezone.utc)
    await db.registrations.update_one(
        {"id": rid},
        {
            "$set": {
                "status": "rejected",
                "rejection_reason": body.reason.strip(),
                "reviewed_by": user["id"],
                "reviewed_by_name": user.get("name") or user["email"],
                "reviewed_at": now,
                "updated_at": now,
            }
        },
    )
    # Revoke any existing pass so a prior-approved QR is immediately refused.
    await db.passes.update_one(
        {"registration_id": rid},
        {"$set": {"active": False, "revoked_at": now}},
    )
    reg2 = await db.registrations.find_one({"id": rid}, {"_id": 0})
    await audit(user["id"], "registration.reject", rid, {"reason": body.reason})
    return RegistrationOut(**(await _enrich_registration(reg2)))


# ---------------------------------------------------------------------------
# SCANNER
# ---------------------------------------------------------------------------
async def _scan_reg(reg: dict) -> dict:
    branch = await db.branches.find_one({"id": reg["branch_id"]}, {"_id": 0, "name": 1})
    return {"full_name": reg["full_name"], "reference": reg["reference"], "batch": reg["batch"], "branch_id": reg["branch_id"], "branch_name": branch["name"] if branch else None}


@api.post("/scan")
async def scan(body: ScanIn, user=Depends(require_roles("super_admin", "coordinator", "scanner"))):
    res = await _do_scan(body, user)
    if res["result"] != "VALID":
        # Log every refused / duplicate attempt (no raw token stored).
        reg = res.get("registration") or {}
        await db.scan_attempts.insert_one(
            {
                "id": "sa-" + pysecrets.token_hex(6),
                "result": res["result"],
                "reference": reg.get("reference"),
                "full_name": reg.get("full_name"),
                "batch": reg.get("batch"),
                "branch_id": reg.get("branch_id"),
                "branch_name": reg.get("branch_name"),
                "attempted_at": datetime.now(timezone.utc),
                "scanner_id": user["id"],
                "scanner_name": user.get("name") or user["email"],
                "station": body.station or "station-1",
            }
        )
    return res


async def _do_scan(body: ScanIn, user: dict) -> dict:
    raw = body.token.strip()
    if re.fullmatch(r"OLM-[0-9A-F]{6}", raw, flags=re.IGNORECASE):
        # Staff manual fallback: look up by registration reference.
        r0 = await db.registrations.find_one({"reference": raw.upper()}, {"_id": 0, "id": 1, "status": 1, "full_name": 1, "reference": 1, "batch": 1, "branch_id": 1})
        if not r0:
            return {"result": "INVALID", "message": "Reference not found"}
        p = await db.passes.find_one({"registration_id": r0["id"]}, {"_id": 0})
        if not p:
            return {"result": "NOT_APPROVED", "message": f"Registration is {r0['status']}", "registration": await _scan_reg(r0)}
    else:
        p = await db.passes.find_one({"token_hash": _hash_pass_token(raw)}, {"_id": 0})
    if not p:
        return {"result": "INVALID", "message": "QR not recognized"}
    reg = await db.registrations.find_one({"id": p["registration_id"]}, {"_id": 0})
    if not reg:
        return {"result": "INVALID", "message": "Registration missing"}
    if not p.get("active"):
        return {
            "result": "REVOKED",
            "message": "This pass has been revoked",
            "registration": await _scan_reg(reg),
        }
    if reg["status"] != "approved":
        return {
            "result": "NOT_APPROVED",
            "message": f"Registration is {reg['status']}",
            "registration": await _scan_reg(reg),
        }
    # Attempt atomic unique insert to prevent duplicate check-in.
    now = datetime.now(timezone.utc)
    try:
        await db.attendance.insert_one(
            {
                "id": "att-" + pysecrets.token_hex(6),
                "registration_id": reg["id"],
                "checked_in_at": now,
                "scanner_id": user["id"],
                "scanner_name": user.get("name") or user["email"],
                "station": body.station or "station-1",
            }
        )
        await audit(user["id"], "attendance.checkin", reg["id"], {"station": body.station})
        return {
            "result": "VALID",
            "message": "Entry approved",
            "checked_in_at": now,
            "registration": await _scan_reg(reg),
        }
    except DuplicateKeyError:
        existing = await db.attendance.find_one({"registration_id": reg["id"]}, {"_id": 0})
        return {
            "result": "ALREADY_CHECKED_IN",
            "message": "Pass already used",
            "checked_in_at": existing["checked_in_at"] if existing else None,
            "scanner_name": existing.get("scanner_name") if existing else None,
            "registration": await _scan_reg(reg),
        }


@api.get("/attendance")
async def attendance_log(
    branch_id: Optional[str] = None,
    user=Depends(require_roles("super_admin", "coordinator")),
):
    """Full check-in log + refused/duplicate scan attempts, branch-scoped."""
    if user["role"] == "coordinator":
        branch_id = user["branch_id"]
    reg_filter = {"branch_id": branch_id} if branch_id else {}
    regs = {
        r["id"]: r
        for r in await db.registrations.find(reg_filter, {"_id": 0, "id": 1, "full_name": 1, "reference": 1, "batch": 1, "branch_id": 1}).to_list(5000)
    }
    branches = {b["id"]: b["name"] for b in await db.branches.find({}, {"_id": 0, "id": 1, "name": 1}).to_list(100)}
    att_filter = {"registration_id": {"$in": list(regs.keys())}} if branch_id else {}
    checkins = []
    for a in await db.attendance.find(att_filter, {"_id": 0}).sort("checked_in_at", -1).to_list(5000):
        r = regs.get(a["registration_id"])
        if not r:
            continue
        checkins.append({
            "id": a["id"], "checked_in_at": a["checked_in_at"], "scanner_name": a.get("scanner_name"),
            "station": a.get("station"), "full_name": r["full_name"], "reference": r["reference"],
            "batch": r["batch"], "branch_name": branches.get(r["branch_id"]),
        })
    attempts = await db.scan_attempts.find({"branch_id": branch_id} if branch_id else {}, {"_id": 0}).sort("attempted_at", -1).to_list(2000)
    return {
        "checkins": checkins,
        "attempts": attempts,
        "duplicate_count": sum(1 for x in attempts if x["result"] == "ALREADY_CHECKED_IN"),
    }


@api.get("/scan/history")
async def scan_history(user=Depends(require_roles("super_admin", "coordinator", "scanner"))):
    filt = {}
    if user["role"] == "coordinator":
        # join via registration branch
        reg_ids = [r["id"] for r in await db.registrations.find({"branch_id": user["branch_id"]}, {"_id": 0, "id": 1}).to_list(5000)]
        filt["registration_id"] = {"$in": reg_ids}
    docs = await db.attendance.find(filt, {"_id": 0}).sort("checked_in_at", -1).limit(100).to_list(100)
    out = []
    for d in docs:
        reg = await db.registrations.find_one({"id": d["registration_id"]}, {"_id": 0, "full_name": 1, "reference": 1, "batch": 1, "branch_id": 1})
        branch = await db.branches.find_one({"id": reg["branch_id"]}, {"_id": 0, "name": 1}) if reg else None
        out.append(
            {
                **d,
                "full_name": reg["full_name"] if reg else "?",
                "reference": reg["reference"] if reg else "?",
                "batch": reg["batch"] if reg else "?",
                "branch_name": branch["name"] if branch else "?",
            }
        )
    return out


# ---------------------------------------------------------------------------
# STATS / DASHBOARD
# ---------------------------------------------------------------------------
@api.get("/stats")
async def stats(user=Depends(require_roles("super_admin", "coordinator"))):
    filt = _branch_filter(user)
    pipeline_status = [{"$match": filt}, {"$group": {"_id": "$status", "n": {"$sum": 1}}}]
    status_counts = {d["_id"]: d["n"] async for d in db.registrations.aggregate(pipeline_status)}
    total = sum(status_counts.values())

    # by branch (admin only)
    by_branch = []
    if user["role"] == "super_admin":
        async for b in db.branches.find({}, {"_id": 0}):
            cnt = await db.registrations.count_documents({"branch_id": b["id"]})
            app_cnt = await db.registrations.count_documents({"branch_id": b["id"], "status": "approved"})
            reg_ids = [r["id"] for r in await db.registrations.find({"branch_id": b["id"]}, {"_id": 0, "id": 1}).to_list(5000)]
            att = await db.attendance.count_documents({"registration_id": {"$in": reg_ids}}) if reg_ids else 0
            by_branch.append({"branch": b["name"], "total": cnt, "approved": app_cnt, "checked_in": att})

    # attendance count
    if user["role"] == "coordinator":
        reg_ids = [r["id"] for r in await db.registrations.find({"branch_id": user["branch_id"]}, {"_id": 0, "id": 1}).to_list(5000)]
        checked = await db.attendance.count_documents({"registration_id": {"$in": reg_ids}}) if reg_ids else 0
    else:
        checked = await db.attendance.count_documents({})

    approved = status_counts.get("approved", 0)
    return {
        "total": total,
        "pending": status_counts.get("pending", 0),
        "approved": approved,
        "rejected": status_counts.get("rejected", 0),
        "checked_in": checked,
        "not_checked_in": max(approved - checked, 0),
        "attendance_pct": round((checked / approved) * 100, 1) if approved else 0.0,
        "by_branch": by_branch,
    }


# ---------------------------------------------------------------------------
# BRANCHES + BATCHES admin
# ---------------------------------------------------------------------------
@api.get("/branches", response_model=List[BranchOut])
async def list_branches(user=Depends(require_roles("super_admin", "coordinator", "scanner"))):
    docs = await db.branches.find({}, {"_id": 0}).to_list(100)
    return [BranchOut(**d) for d in docs]


@api.post("/branches", response_model=BranchOut)
async def create_branch(body: BranchIn, user=Depends(require_roles("super_admin"))):
    doc = {
        "id": "br-" + pysecrets.token_hex(4),
        "name": body.name.strip(),
        "active": body.active,
        "created_at": datetime.now(timezone.utc),
    }
    try:
        await db.branches.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(409, "Branch name already exists")
    await audit(user["id"], "branch.create", doc["id"])
    return BranchOut(**doc)


@api.patch("/branches/{bid}", response_model=BranchOut)
async def update_branch(bid: str, body: BranchIn, user=Depends(require_roles("super_admin"))):
    try:
        r = await db.branches.find_one_and_update(
            {"id": bid},
            {"$set": {"name": body.name.strip(), "active": body.active}},
            return_document=ReturnDocument.AFTER,
            projection={"_id": 0},
        )
    except DuplicateKeyError:
        raise HTTPException(409, "Another branch already has this name")
    if not r:
        raise HTTPException(404, "Not found")
    await audit(user["id"], "branch.update", bid)
    return BranchOut(**r)


@api.get("/batches", response_model=List[BatchOut])
async def list_batches(user=Depends(require_roles("super_admin", "coordinator", "scanner"))):
    docs = await db.batches.find({}, {"_id": 0}).to_list(200)
    return [BatchOut(**d) for d in docs]


@api.post("/batches", response_model=BatchOut)
async def create_batch(body: BatchIn, user=Depends(require_roles("super_admin"))):
    doc = {"id": "bt-" + pysecrets.token_hex(4), "name": body.name.strip()}
    try:
        await db.batches.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(409, "Batch already exists")
    return BatchOut(**doc)


@api.delete("/batches/{batch_id}")
async def delete_batch(batch_id: str, user=Depends(require_roles("super_admin"))):
    await db.batches.delete_one({"id": batch_id})
    return {"ok": True}


# ---------------------------------------------------------------------------
# STAFF management (super admin)
# ---------------------------------------------------------------------------
async def _check_coordinator_branch(role: str, branch_id: Optional[str]):
    if role == "coordinator":
        if not branch_id or not await db.branches.find_one({"id": branch_id}):
            raise HTTPException(400, "Coordinators must be assigned to an existing branch")


@api.get("/staff", response_model=List[UserOut])
async def list_staff(user=Depends(require_roles("super_admin"))):
    docs = await db.users.find({}, {"_id": 0, "password_hash": 0}).to_list(200)
    return [UserOut(**d) for d in docs]


@api.post("/staff", response_model=UserOut)
async def create_staff(body: StaffCreateIn, user=Depends(require_roles("super_admin"))):
    await _check_coordinator_branch(body.role, body.branch_id)
    doc = {
        "id": "u-" + pysecrets.token_hex(6),
        "email": body.email.lower().strip(),
        "name": body.name.strip(),
        "role": body.role,
        "branch_id": body.branch_id,
        "can_export": body.can_export,
        "must_change_password": True,
        "password_hash": _hash_password(body.password),
        "active": True,
        "created_at": datetime.now(timezone.utc),
    }
    try:
        await db.users.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(409, "Email already registered")
    await audit(user["id"], "staff.create", doc["id"])
    doc.pop("password_hash", None)
    return UserOut(**doc)


@api.patch("/staff/{uid}", response_model=UserOut)
async def update_staff(uid: str, body: StaffUpdateIn, user=Depends(require_roles("super_admin"))):
    current = await db.users.find_one({"id": uid}, {"_id": 0, "role": 1, "branch_id": 1, "active": 1})
    if not current:
        raise HTTPException(404, "Not found")
    demoting = current["role"] == "super_admin" and (
        (body.role is not None and body.role != "super_admin") or body.active is False
    )
    if demoting:
        if uid == user["id"]:
            raise HTTPException(400, "You cannot demote or deactivate your own admin account")
        if await db.users.count_documents({"role": "super_admin", "active": True}) <= 1:
            raise HTTPException(400, "At least one active super admin must remain")
    await _check_coordinator_branch(body.role or current["role"], body.branch_id if body.branch_id is not None else current.get("branch_id"))
    upd = {k: v for k, v in body.model_dump(exclude_unset=True).items() if k != "password"}
    if body.password:
        upd["password_hash"] = _hash_password(body.password)
        upd["must_change_password"] = True  # admin-set password must be changed by the owner
    r = await db.users.find_one_and_update(
        {"id": uid}, {"$set": upd}, return_document=ReturnDocument.AFTER, projection={"_id": 0, "password_hash": 0}
    )
    if not r:
        raise HTTPException(404, "Not found")
    await audit(user["id"], "staff.update", uid)
    return UserOut(**r)


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# FACULTY REPORT
# ---------------------------------------------------------------------------
async def _faculty_rows(user: dict, branch_id: Optional[str]) -> list:
    filt = _branch_filter(user)
    if user["role"] == "super_admin" and branch_id:
        filt["branch_id"] = branch_id
    filt["faculty_name"] = {"$exists": True, "$ne": None}
    branches = {b["id"]: b["name"] for b in await db.branches.find({}, {"_id": 0, "id": 1, "name": 1}).to_list(100)}
    checked = {a["registration_id"] for a in await db.attendance.find({}, {"_id": 0, "registration_id": 1}).to_list(10000)}
    groups: dict = {}
    for r in await db.registrations.find(filt, {"_id": 0, "id": 1, "branch_id": 1, "faculty_name": 1, "status": 1}).to_list(10000):
        display = re.sub(r"\s+", " ", (r.get("faculty_name") or "").strip())
        if not display:
            continue
        key = (r["branch_id"], display.lower())
        g = groups.setdefault(key, {
            "branch_id": r["branch_id"], "branch_name": branches.get(r["branch_id"], "?"), "faculty_name": display,
            "total": 0, "approved": 0, "pending": 0, "rejected": 0, "checked_in": 0,
        })
        g["total"] += 1
        g[r["status"]] = g.get(r["status"], 0) + 1
        if r["id"] in checked:
            g["checked_in"] += 1
    return sorted(groups.values(), key=lambda g: (g["branch_name"], -g["total"], g["faculty_name"].lower()))


@api.get("/reports/faculty")
async def faculty_report(branch_id: Optional[str] = None, user=Depends(require_roles("super_admin", "coordinator"))):
    rows = await _faculty_rows(user, branch_id)
    return {"rows": rows, "total_students": sum(r["total"] for r in rows), "faculty_count": len(rows)}


@api.get("/export/faculty.csv")
async def export_faculty(branch_id: Optional[str] = None, user=Depends(require_roles("super_admin", "coordinator"))):
    if user["role"] == "coordinator" and not user.get("can_export"):
        raise HTTPException(403, "CSV download has not been enabled for your account by the admin")
    rows = await _faculty_rows(user, branch_id)
    buf = io.StringIO()
    w = csv.writer(buf, quoting=csv.QUOTE_ALL)
    w.writerow(["Branch", "Faculty Name", "Total Students", "Approved", "Pending", "Rejected", "Checked In"])
    for r in rows:
        w.writerow([_csv_safe(v) for v in [r["branch_name"], r["faculty_name"], r["total"], r["approved"], r["pending"], r["rejected"], r["checked_in"]]])
    await audit(user["id"], "export.faculty_csv", None, {"rows": len(rows)})
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=olam-faculty-report.csv"},
    )


# EVENT DAY SUMMARY (attendance by branch and batch)
# ---------------------------------------------------------------------------
def _att_row(**kw) -> dict:
    return {**kw, "registered": 0, "approved": 0, "checked_in": 0}


async def _event_day_summary(user: dict) -> dict:
    filt = _branch_filter(user)
    branches = {b["id"]: b["name"] for b in await db.branches.find({}, {"_id": 0, "id": 1, "name": 1}).to_list(100)}
    att = {a["registration_id"]: a["checked_in_at"] for a in await db.attendance.find({}, {"_id": 0, "registration_id": 1, "checked_in_at": 1}).to_list(20000)}
    by_branch: dict = {}
    by_batch: dict = {}
    by_pair: dict = {}
    total = _att_row()
    first = last = None
    # Show every branch in scope, even ones with no registrations yet.
    for bid, bname in branches.items():
        if not filt or filt.get("branch_id") == bid:
            by_branch.setdefault(bname, _att_row(branch_name=bname))
    for r in await db.registrations.find(filt, {"_id": 0, "id": 1, "branch_id": 1, "batch": 1, "status": 1}).to_list(20000):
        bname = branches.get(r["branch_id"], "?")
        batch = r.get("batch") or "?"
        rows = [
            total,
            by_branch.setdefault(bname, _att_row(branch_name=bname)),
            by_batch.setdefault(batch, _att_row(batch=batch)),
            by_pair.setdefault((bname, batch), _att_row(branch_name=bname, batch=batch)),
        ]
        approved = r["status"] == "approved"
        present = approved and r["id"] in att
        for row in rows:
            row["registered"] += 1
            if approved:
                row["approved"] += 1
            if present:
                row["checked_in"] += 1
        t = att.get(r["id"]) if present else None
        if t:
            first = t if first is None or t < first else first
            last = t if last is None or t > last else last

    def fin(rows):
        for x in rows:
            x["absent"] = max(x["approved"] - x["checked_in"], 0)
            x["attendance_pct"] = round(x["checked_in"] / x["approved"] * 100, 1) if x["approved"] else 0.0
        return rows

    return {
        "generated_at": datetime.now(timezone.utc),
        "totals": fin([total])[0],
        "first_checkin": first,
        "last_checkin": last,
        "by_branch": fin(sorted(by_branch.values(), key=lambda x: x["branch_name"])),
        "by_batch": fin(sorted(by_batch.values(), key=lambda x: x["batch"])),
        "by_branch_batch": fin(sorted(by_pair.values(), key=lambda x: (x["branch_name"], x["batch"]))),
    }


@api.get("/reports/event-day")
async def event_day_report(user=Depends(require_roles("super_admin", "coordinator"))):
    return await _event_day_summary(user)


@api.get("/export/event-day.csv")
async def export_event_day(user=Depends(require_roles("super_admin", "coordinator"))):
    if user["role"] == "coordinator" and not user.get("can_export"):
        raise HTTPException(403, "CSV download has not been enabled for your account by the admin")
    s = await _event_day_summary(user)
    buf = io.StringIO()
    w = csv.writer(buf, quoting=csv.QUOTE_ALL)
    w.writerow(["Branch", "Batch", "Registered", "Approved", "Checked In", "Absent", "Attendance %"])
    for r in s["by_branch_batch"]:
        w.writerow([_csv_safe(v) for v in [r["branch_name"], r["batch"], r["registered"], r["approved"], r["checked_in"], r["absent"], r["attendance_pct"]]])
    for r in s["by_branch"]:
        w.writerow([_csv_safe(v) for v in [r["branch_name"], "ALL BATCHES", r["registered"], r["approved"], r["checked_in"], r["absent"], r["attendance_pct"]]])
    t = s["totals"]
    w.writerow(["ALL BRANCHES", "ALL BATCHES", t["registered"], t["approved"], t["checked_in"], t["absent"], t["attendance_pct"]])
    await audit(user["id"], "export.event_day_csv", None, {})
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=olam-event-day-summary.csv"},
    )


# CSV export
# ---------------------------------------------------------------------------
@api.get("/export/registrations.csv")
async def export_regs(user=Depends(require_roles("super_admin", "coordinator"))):
    if user["role"] == "coordinator" and not user.get("can_export"):
        raise HTTPException(403, "CSV download has not been enabled for your account by the admin")
    filt = _branch_filter(user)
    docs = await db.registrations.find(filt, {"_id": 0}).to_list(5000)
    buf = io.StringIO()
    w = csv.writer(buf, quoting=csv.QUOTE_ALL)
    w.writerow(["Reference", "Name", "Mobile", "Email", "Branch", "Batch", "Batch No.", "Faculty Name", "Status", "Reviewed By", "Checked In At", "Created At"])
    for d in docs:
        branch = await db.branches.find_one({"id": d["branch_id"]}, {"_id": 0, "name": 1})
        att = await db.attendance.find_one({"registration_id": d["id"]}, {"_id": 0})
        # Neutralise spreadsheet formulas in any user-supplied cell (CSV injection).
        w.writerow([_csv_safe(v) for v in [
            d["reference"], d["full_name"], d["mobile"], d["email"],
            branch["name"] if branch else "", d["batch"], d.get("batch_no") or "", d.get("faculty_name") or "", d["status"],
            d.get("reviewed_by_name") or "",
            att["checked_in_at"].isoformat() if att else "",
            d["created_at"].isoformat(),
        ]])
    await audit(user["id"], "export.csv", None, {"rows": len(docs)})
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=olam-registrations.csv"},
    )


# ---------------------------------------------------------------------------
# Audit log view
# ---------------------------------------------------------------------------
@api.get("/audit")
async def view_audit(user=Depends(require_roles("super_admin"))):
    docs = await db.audit_logs.find({}, {"_id": 0}).sort("timestamp", -1).limit(200).to_list(200)
    return docs


# ---------------------------------------------------------------------------
# Wire up
# ---------------------------------------------------------------------------
app.include_router(api)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=False,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
