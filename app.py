"""
app.py — Online license validation server for Bank Audit SaaS.

Deploy this on Render as a Flask/Gunicorn web service.

Endpoints:
    POST /validate          — client app calls this once per day
    POST /admin/register    — register / sync a license from admin panel
    POST /admin/extend      — extend a license's expiry remotely
    POST /admin/revoke      — revoke a license immediately
    POST /admin/restore     — re-activate a revoked license
    GET  /admin/list        — list all licenses (for your own dashboard)

Admin endpoints require the X-Admin-Key header matching ADMIN_KEY below.
"""

import os, datetime
from flask import Flask, request, jsonify
from db import (
    init_db, get_license, upsert_license, set_active, set_machine_id,
    extend_license, touch_last_seen, list_licenses,
)

app = Flask(__name__)

# ── Change this to a long random secret before deploying ──────────
ADMIN_KEY = os.environ.get("ADMIN_KEY", "change-this-secret-key-before-deploy")


def _admin_auth():
    """Return True if the request carries the correct admin key."""
    return request.headers.get("X-Admin-Key", "") == ADMIN_KEY


# ─────────────────────────────────────────────────────────────────
# Health check — browser-friendly status page
# ─────────────────────────────────────────────────────────────────

@app.route("/", methods=["GET"])
def index():
    return (
        "<html><body style='font-family:sans-serif;padding:40px'>"
        "<h2>&#x2705; Bank Audit License Server</h2>"
        "<p>Server is <strong>online</strong>.</p>"
        "<ul>"
        "<li><code>POST /validate</code> — client license check</li>"
        "<li><code>POST /admin/register</code> — register license</li>"
        "<li><code>POST /admin/revoke</code> — revoke license</li>"
        "<li><code>POST /admin/restore</code> — restore license</li>"
        "<li><code>POST /admin/extend</code> — extend license</li>"
        "<li><code>GET  /admin/list</code> — list all licenses</li>"
        "</ul>"
        "</body></html>"
    ), 200


# ─────────────────────────────────────────────────────────────────
# Client endpoint — called by the desktop app once per day
# ─────────────────────────────────────────────────────────────────

@app.route("/validate", methods=["POST"])
def validate():
    data = request.get_json(force=True, silent=True) or {}
    username = str(data.get("username", "")).lower().strip()
    code = str(data.get("code", "")).strip()
    machine_id = str(data.get("machine_id", "")).upper().strip()

    if not username or not code:
        return jsonify({"valid": False, "reason": "missing_fields"}), 400

    record = get_license(code)

    if record is None:
        return jsonify({"valid": False, "reason": "not_registered"}), 200

    if record["username"] != username:
        return jsonify({"valid": False, "reason": "username_mismatch"}), 200

    if not record["is_active"]:
        return jsonify({"valid": False, "reason": "revoked"}), 200

    record_machine_id = str(record.get("machine_id", "")).upper().strip()
    if record_machine_id and machine_id and record_machine_id != machine_id:
        return jsonify({"valid": False, "reason": "machine_mismatch"}), 200
    if record_machine_id and not machine_id:
        return jsonify({"valid": False, "reason": "missing_machine_id"}), 200
    if not record_machine_id and machine_id:
        set_machine_id(code, machine_id)
        record["machine_id"] = machine_id

    expiry = datetime.date.fromisoformat(record["expiry"])
    today = datetime.date.today()

    if today > expiry:
        days_ago = (today - expiry).days
        return jsonify({
            "valid": False,
            "reason": "expired",
            "days_ago": days_ago,
            "expiry": record["expiry"],
        }), 200

    days_left = (expiry - today).days
    touch_last_seen(code)

    return jsonify({
        "valid": True,
        "expiry": record["expiry"],
        "days_left": days_left,
        "machine_id": record.get("machine_id", ""),
    }), 200


# ─────────────────────────────────────────────────────────────────
# Admin endpoints — only you use these
# ─────────────────────────────────────────────────────────────────

@app.route("/admin/register", methods=["POST"])
def admin_register():
    """Sync a newly generated license to the server database."""
    if not _admin_auth():
        return jsonify({"error": "unauthorized"}), 401
    data = request.get_json(force=True, silent=True) or {}
    username = str(data.get("username", "")).lower().strip()
    code = str(data.get("code", "")).strip()
    expiry = str(data.get("expiry", "")).strip()     # YYYY-MM-DD
    machine_id = str(data.get("machine_id", "")).strip()

    if not username or not code or not expiry:
        return jsonify({"error": "missing fields: username, code, expiry required"}), 400

    try:
        datetime.date.fromisoformat(expiry)
    except ValueError:
        return jsonify({"error": "expiry must be YYYY-MM-DD"}), 400

    upsert_license(username, code, expiry, machine_id)
    return jsonify({"ok": True, "message": f"License registered for {username}, expires {expiry}"}), 200


@app.route("/admin/extend", methods=["POST"])
def admin_extend():
    """Extend (or renew) a license to a new expiry date."""
    if not _admin_auth():
        return jsonify({"error": "unauthorized"}), 401
    data = request.get_json(force=True, silent=True) or {}
    code = str(data.get("code", "")).strip()
    new_expiry = str(data.get("new_expiry", "")).strip()   # YYYY-MM-DD

    if not code or not new_expiry:
        return jsonify({"error": "missing fields: code, new_expiry required"}), 400

    try:
        datetime.date.fromisoformat(new_expiry)
    except ValueError:
        return jsonify({"error": "new_expiry must be YYYY-MM-DD"}), 400

    record = get_license(code)
    if record is None:
        return jsonify({"error": "license not found"}), 404

    extend_license(code, new_expiry)
    return jsonify({"ok": True, "message": f"License extended to {new_expiry}"}), 200


@app.route("/admin/revoke", methods=["POST"])
def admin_revoke():
    """Revoke a license — client will be blocked on next daily check."""
    if not _admin_auth():
        return jsonify({"error": "unauthorized"}), 401
    data = request.get_json(force=True, silent=True) or {}
    code = str(data.get("code", "")).strip()

    if not code:
        return jsonify({"error": "missing field: code"}), 400

    record = get_license(code)
    if record is None:
        return jsonify({"error": "license not found"}), 404

    set_active(code, False)
    return jsonify({"ok": True, "message": "License revoked"}), 200


@app.route("/admin/restore", methods=["POST"])
def admin_restore():
    """Re-activate a previously revoked license."""
    if not _admin_auth():
        return jsonify({"error": "unauthorized"}), 401
    data = request.get_json(force=True, silent=True) or {}
    code = str(data.get("code", "")).strip()

    if not code:
        return jsonify({"error": "missing field: code"}), 400

    record = get_license(code)
    if record is None:
        return jsonify({"error": "license not found"}), 404

    set_active(code, True)
    return jsonify({"ok": True, "message": "License restored"}), 200


@app.route("/admin/list", methods=["GET"])
def admin_list():
    """Return all license records."""
    if not _admin_auth():
        return jsonify({"error": "unauthorized"}), 401
    return jsonify(list_licenses()), 200


# ─────────────────────────────────────────────────────────────────
# Startup
# ─────────────────────────────────────────────────────────────────

init_db()

if __name__ == "__main__":
    app.run(debug=False, port=5000)
