# OLAM 3.0 – THE GRAND WEDDING (Delta Academy)

## Original problem
Online student registration, branch coordinator approval, secure QR pass, duplicate-safe event-day QR check-in, dashboards, CSV export for 500–1,000 students across 3 branches. Roles: super admin, coordinator, scanner, student.

## User choices
- Expo (mobile + web), FastAPI + MongoDB + JWT (instead of Supabase)
- Emergent-managed Resend email for pass links + secure retrieval page
- Super admin: amalgkrishnaadmin@olam.delta / Admin@12345
- Navy / champagne gold / ivory, Playfair Display + Inter, user friendly

## Architecture
- backend/server.py: JWT (HS256, bcrypt), role deps enforced server-side; coordinators scoped to branch_id on every query/action.
- Collections: users, branches, batches, registrations (unique branch_id+student_code, unique reference), passes (HMAC-SHA256 token_hash, unique registration_id, active/revoked_at), attendance (UNIQUE registration_id → atomic duplicate prevention), audit_logs.
- Pass token: 192-bit random (secrets.token_urlsafe(24)); QR contains only opaque token. Rejecting revokes pass immediately; re-approval issues a new token.
- Pass retrieval: /my-pass (reference + matching email → token); email link sent on approval (background task).
- Scanner role cannot list registrations (only scan + scan history). Coordinators must have a valid branch.
- Scanner: expo-camera (native + web), manual token / OLM-reference fallback; results VALID / ALREADY_CHECKED_IN / NOT_APPROVED / REVOKED / INVALID / ERROR (never auto-approves on error).

## Implemented (Oct 2026)
- Landing, Register, Confirmation, Status/Retrieve, QR Pass, Staff Login, Dashboard (overview stats, by-branch, registrations w/ search/filter/approve/reject-with-reason, settings: branches/batches), Staff management, Scanner + recent check-ins, CSV export (web), audit log API.

## Notes / limits
- Plain pass token stored alongside hash to allow student re-retrieval (documented trade-off).
- Email subject to Emergent credit balance; failures don't block approval.
- No offline validation; network errors show "go to exception desk".

## Backlog
- P1: Attendance history page w/ duplicate attempt log, audit log viewer UI, branch rename/deactivate UI, event settings (registration open/close toggle), coordinator CSV permission toggle
- P1: Rate limiting on public lookup / login
- P2: Profile photo upload, pagination, registration trends chart, printable pass
- Branches renamed to KALOOR (br-1), ELAMAKKARA (br-2), MUVATTUPUZHA (br-3)
