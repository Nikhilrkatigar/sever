"""
MongoDB helpers for the online license server.

Environment variables:
    MONGODB_URI   MongoDB Atlas connection string
    MONGODB_DB    Database name, defaults to bank_audit_licensing

Collection: licenses
    username     lowercase username
    code         full AUDIT-XXXXX license code, unique
    expiry       ISO date YYYY-MM-DD
    machine_id   16-char machine id, empty until bound
    is_active    true/false
    last_seen    UTC ISO datetime of last /validate call
    created      ISO date of record creation
"""

import datetime
import os

from pymongo import ASCENDING, MongoClient


_MONGODB_URI = os.environ.get("MONGODB_URI", "").strip()
_MONGODB_DB = os.environ.get("MONGODB_DB", "bank_audit_licensing").strip()

if not _MONGODB_URI:
    raise RuntimeError("MONGODB_URI environment variable is required for the license server.")

_CLIENT = MongoClient(_MONGODB_URI, serverSelectionTimeoutMS=8000)
_DB = _CLIENT[_MONGODB_DB]
_LICENSES = _DB["licenses"]


def init_db():
    _LICENSES.create_index([("code", ASCENDING)], unique=True)
    _LICENSES.create_index([("username", ASCENDING)])


def upsert_license(username: str, code: str, expiry: str, machine_id: str = ""):
    username = username.lower().strip()
    code = code.strip()
    machine_id = machine_id.upper().strip()
    today = datetime.date.today().isoformat()
    _LICENSES.update_one(
        {"code": code},
        {
            "$set": {
                "username": username,
                "expiry": expiry,
                "machine_id": machine_id,
                "is_active": True,
            },
            "$setOnInsert": {"created": today},
        },
        upsert=True,
    )


def get_license(code: str) -> dict | None:
    record = _LICENSES.find_one({"code": code.strip()}, {"_id": False})
    if record is None:
        return None
    record["is_active"] = bool(record.get("is_active", True))
    record.setdefault("machine_id", "")
    record.setdefault("last_seen", "")
    record.setdefault("created", "")
    return record


def set_active(code: str, active: bool):
    _LICENSES.update_one({"code": code.strip()}, {"$set": {"is_active": bool(active)}})


def set_machine_id(code: str, machine_id: str):
    _LICENSES.update_one(
        {"code": code.strip()},
        {"$set": {"machine_id": machine_id.upper().strip()}},
    )


def extend_license(code: str, new_expiry: str):
    _LICENSES.update_one(
        {"code": code.strip()},
        {"$set": {"expiry": new_expiry, "is_active": True}},
    )


def touch_last_seen(code: str):
    _LICENSES.update_one(
        {"code": code.strip()},
        {"$set": {"last_seen": datetime.datetime.utcnow().isoformat(timespec="seconds")}},
    )


def list_licenses() -> list[dict]:
    cursor = _LICENSES.find({}, {"_id": False}).sort("username", ASCENDING)
    records = list(cursor)
    for record in records:
        record["is_active"] = bool(record.get("is_active", True))
        record.setdefault("machine_id", "")
        record.setdefault("last_seen", "")
        record.setdefault("created", "")
    return records
