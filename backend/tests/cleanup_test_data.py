# Removes TEST_-prefixed data created by test_olam_api.py and UI tests
import asyncio
import os
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")


async def main():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    regs = await db.registrations.find({"full_name": {"$regex": "^TEST"}}, {"_id": 0, "id": 1}).to_list(10000)
    ids = [r["id"] for r in regs]
    print("regs", (await db.registrations.delete_many({"id": {"$in": ids}})).deleted_count)
    print("passes", (await db.passes.delete_many({"registration_id": {"$in": ids}})).deleted_count)
    print("attendance", (await db.attendance.delete_many({"registration_id": {"$in": ids}})).deleted_count)
    print("scan_attempts", (await db.scan_attempts.delete_many({"$or": [{"registration_id": {"$in": ids}}, {"full_name": {"$regex": "^TEST"}}, {"scanner_name": {"$regex": "^TEST"}}, {"station": {"$regex": "^TEST"}}]})).deleted_count)
    print("users", (await db.users.delete_many({"email": {"$regex": "^test_"}})).deleted_count)
    print("branches", (await db.branches.delete_many({"name": {"$regex": "^TEST"}})).deleted_count)
    print("batches", (await db.batches.delete_many({"name": {"$regex": "^TEST"}})).deleted_count)


asyncio.run(main())
