"""OLAM 3.0 - THE GRAND WEDDING  (FastAPI backend)

Features: role-based JWT auth, student registration, coordinator approval,
secure QR pass issuance + validation, duplicate-safe check-in, admin stats,
CSV export, audit log, Resend transactional email for pass delivery.
"""
from __future__ import annotations

import os
import re
import asyncio
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


def _ref_code() -> str:
    # Public registration reference, e.g. OLM-7F3K2A
    return "OLM-" + pysecrets.token_hex(3).upper()


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, max_length=72)


class UserOut(BaseModel):
    id: str
    email: EmailStr
    role: Role
    name: Optional[str] = None
    branch_id: Optional[str] = None
    active: bool = True


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class BranchIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    active: bool = True


class BranchOut(BaseModel):
    id: str
    name: str
    active: bool
    created_at: datetime


class BatchIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class BatchOut(BaseModel):
    id: str
    name: str


class StaffCreateIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)
    name: str
    role: Literal["super_admin", "coordinator", "scanner"]
    branch_id: Optional[str] = None


class StaffUpdateIn(BaseModel):
    name: Optional[str] = None
    role: Optional[Literal["super_admin", "coordinator", "scanner"]] = None
    branch_id: Optional[str] = None
    active: Optional[bool] = None
    password: Optional[str] = Field(default=None, min_length=8, max_length=72)


class RegistrationIn(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    student_code: str = Field(min_length=2, max_length=40)
    mobile: str = Field(min_length=5, max_length=20)
    email: EmailStr
    branch_id: str
    batch: str = Field(min_length=1, max_length=80)
    confirm: bool

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
    student_code: str
    mobile: str
    email: EmailStr
    branch_id: str
    branch_name: Optional[str] = None
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
    await db.registrations.create_index(
        [("branch_id", 1), ("student_code", 1)], unique=True
    )
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
    # Seed default batches
    for b in ["Batch A", "Batch B", "Batch C", "Alumni"]:
        if not await db.batches.find_one({"name": b}):
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
                "created_at": datetime.now(timezone.utc),
            }
        )
        logger.info("Seeded super admin: %s", admin_email)


@app.on_event("shutdown")
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
async def login(body: LoginIn):
    email = body.email.lower().strip()
    user = await db.users.find_one({"email": email})
    if not user or not user.get("active", True) or not _verify_password(body.password, user["password_hash"]):
        raise HTTPException(401, "Invalid credentials")
    if user["role"] not in STAFF_ROLES:
        raise HTTPException(403, "Staff login only")
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
        },
    }


@api.get("/auth/me", response_model=UserOut)
async def me(user=Depends(current_user)):
    return UserOut(**user)


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
# REGISTRATION (public submit, status, pass retrieval)
# ---------------------------------------------------------------------------
async def _send_pass_email(reg: dict, pass_token: str) -> None:
    """Fire-and-forget email to approved student with pass link."""
    if not EMAIL_KEY or not APP_PUBLIC_URL:
        logger.info("Email skipped (no key or public url)")
        return
    link = f"{APP_PUBLIC_URL}/pass?ref={reg['reference']}&t={pass_token}"
    html = (
        f'<table role="presentation" width="100%" style="background:#FDFBF7;padding:0;margin:0">'
        f'<tr><td align="center" style="padding:32px 16px;font-family:Arial,sans-serif;color:#0B192C">'
        f'<table role="presentation" width="100%" style="max-width:540px;background:#FFFFFF;border:1px solid #E5E0D8;border-radius:16px;padding:28px">'
        f'<tr><td style="text-align:center">'
        f'<p style="font-size:12px;letter-spacing:4px;color:#D4AF37;margin:0">DELTA ACADEMY PRESENTS</p>'
        f'<h1 style="font-family:Georgia,serif;font-size:28px;margin:6px 0 2px 0;color:#0B192C">OLAM 3.0</h1>'
        f'<p style="font-size:12px;letter-spacing:3px;color:#5C6B82;margin:0 0 20px 0">THE GRAND WEDDING</p>'
        f'<p style="font-size:16px;margin:0 0 8px 0">Namaste {reg["full_name"].split()[0]},</p>'
        f'<p style="font-size:14px;color:#374151;line-height:22px;margin:0 0 20px 0">Your registration has been <strong style="color:#10B981">approved</strong>. Your digital QR pass is ready. Please present it at the entrance on event day.</p>'
        f'<a href="{link}" style="display:inline-block;background:#D4AF37;color:#0B192C;text-decoration:none;padding:14px 28px;border-radius:999px;font-weight:bold;font-size:14px">View My Digital Pass</a>'
        f'<p style="font-size:12px;color:#5C6B82;margin:24px 0 0 0">Reference: <strong>{reg["reference"]}</strong></p>'
        f'<p style="font-size:11px;color:#9CA3AF;margin:20px 0 0 0">Sent by {EMAIL_FROM_NAME}. We never ask for your password by email.</p>'
        f"</td></tr></table></td></tr></table>"
    )
    payload = {
        "to": [reg["email"]],
        "subject": "Your OLAM 3.0 pass is ready",
        "html": html,
        "from_name": EMAIL_FROM_NAME,
    }
    try:
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.post(
                f"{EMAIL_BASE_URL}/api/v1/email/send",
                headers={"X-Email-Key": EMAIL_KEY},
                json=payload,
            )
            if r.status_code >= 300:
                logger.warning("Email send failed: %s %s", r.status_code, r.text[:300])
    except Exception as e:
        logger.warning("Email send error: %s", e)


@api.post("/registrations", response_model=RegistrationOut)
async def submit_registration(body: RegistrationIn):
    branch = await db.branches.find_one({"id": body.branch_id, "active": True})
    if not branch:
        raise HTTPException(400, "Invalid branch")
    phone = _normalize_phone(body.mobile)
    now = datetime.now(timezone.utc)
    reg = {
        "id": "reg-" + pysecrets.token_hex(6),
        "reference": _ref_code(),
        "full_name": body.full_name.strip(),
        "student_code": body.student_code.strip().upper(),
        "mobile": phone,
        "email": body.email.lower().strip(),
        "branch_id": body.branch_id,
        "batch": body.batch,
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
        raise HTTPException(409, "A registration with this student ID already exists for this branch.")
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
async def lookup_registration(body: PassLookupIn):
    """Public retrieval. Requires reference AND matching email, returns status
    and (if approved) the one-time pass token (shown only to the student)."""
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
        if pass_doc and pass_doc.get("plain_token"):
            # Only the student can retrieve the plain token via their email.
            out["pass_token"] = pass_doc["plain_token"]
    return out


@api.get("/pass/verify/{token}")
async def pass_verify_public(token: str):
    """Student app uses this to show the live pass detail without authentication,
    using the token itself as proof-of-possession. Does NOT check in."""
    th = _hash_pass_token(token)
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
            {"student_code": rx},
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
    """Create or reactivate a pass; returns the plain token (one-time retrieval)."""
    existing = await db.passes.find_one({"registration_id": reg["id"]})
    plain = pysecrets.token_urlsafe(24)
    th = _hash_pass_token(plain)
    now = datetime.now(timezone.utc)
    if existing:
        await db.passes.update_one(
            {"registration_id": reg["id"]},
            {"$set": {"token_hash": th, "plain_token": plain, "active": True, "revoked_at": None, "issued_at": now}},
        )
    else:
        await db.passes.insert_one(
            {
                "id": "ps-" + pysecrets.token_hex(6),
                "registration_id": reg["id"],
                "token_hash": th,
                "plain_token": plain,  # one-time retrieval; shown via email + status page only
                "active": True,
                "issued_at": now,
                "revoked_at": None,
            }
        )
    return plain


@api.post("/registrations/{rid}/approve", response_model=RegistrationOut)
async def approve_registration(rid: str, user=Depends(require_roles("super_admin", "coordinator"))):
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
    # Fire email in the background so approval never waits on the provider.
    asyncio.create_task(_send_pass_email(reg2, plain))
    return RegistrationOut(**(await _enrich_registration(reg2)))


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
    return {"full_name": reg["full_name"], "reference": reg["reference"], "batch": reg["batch"], "branch_name": branch["name"] if branch else None}


@api.post("/scan")
async def scan(body: ScanIn, user=Depends(require_roles("super_admin", "coordinator", "scanner"))):
    raw = body.token.strip()
    if re.fullmatch(r"OLM-[0-9A-Fa-f]{6}", raw):
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
        branch = await db.branches.find_one({"id": reg["branch_id"]}, {"_id": 0, "name": 1})
        return {
            "result": "VALID",
            "message": "Entry approved",
            "checked_in_at": now,
            "registration": {
                "full_name": reg["full_name"],
                "reference": reg["reference"],
                "batch": reg["batch"],
                "branch_name": branch["name"] if branch else None,
            },
        }
    except DuplicateKeyError:
        existing = await db.attendance.find_one({"registration_id": reg["id"]}, {"_id": 0})
        branch = await db.branches.find_one({"id": reg["branch_id"]}, {"_id": 0, "name": 1})
        return {
            "result": "ALREADY_CHECKED_IN",
            "message": "Pass already used",
            "checked_in_at": existing["checked_in_at"] if existing else None,
            "scanner_name": existing.get("scanner_name") if existing else None,
            "registration": {
                "full_name": reg["full_name"],
                "reference": reg["reference"],
                "batch": reg["batch"],
                "branch_name": branch["name"] if branch else None,
            },
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
    r = await db.branches.find_one_and_update(
        {"id": bid},
        {"$set": {"name": body.name.strip(), "active": body.active}},
        return_document=ReturnDocument.AFTER,
        projection={"_id": 0},
    )
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
    current = await db.users.find_one({"id": uid}, {"_id": 0, "role": 1, "branch_id": 1})
    if not current:
        raise HTTPException(404, "Not found")
    await _check_coordinator_branch(body.role or current["role"], body.branch_id if body.branch_id is not None else current.get("branch_id"))
    upd = {k: v for k, v in body.model_dump(exclude_unset=True).items() if k != "password"}
    if body.password:
        upd["password_hash"] = _hash_password(body.password)
    r = await db.users.find_one_and_update(
        {"id": uid}, {"$set": upd}, return_document=ReturnDocument.AFTER, projection={"_id": 0, "password_hash": 0}
    )
    if not r:
        raise HTTPException(404, "Not found")
    await audit(user["id"], "staff.update", uid)
    return UserOut(**r)


# ---------------------------------------------------------------------------
# CSV export
# ---------------------------------------------------------------------------
@api.get("/export/registrations.csv")
async def export_regs(user=Depends(require_roles("super_admin", "coordinator"))):
    filt = _branch_filter(user)
    docs = await db.registrations.find(filt, {"_id": 0}).to_list(5000)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Reference", "Name", "Student ID", "Mobile", "Email", "Branch", "Batch", "Status", "Reviewed By", "Checked In At", "Created At"])
    for d in docs:
        branch = await db.branches.find_one({"id": d["branch_id"]}, {"_id": 0, "name": 1})
        att = await db.attendance.find_one({"registration_id": d["id"]}, {"_id": 0})
        w.writerow(
            [
                d["reference"], d["full_name"], d["student_code"], d["mobile"], d["email"],
                branch["name"] if branch else "", d["batch"], d["status"],
                d.get("reviewed_by_name") or "",
                att["checked_in_at"].isoformat() if att else "",
                d["created_at"].isoformat(),
            ]
        )
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
