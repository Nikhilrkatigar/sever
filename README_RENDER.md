# Bank Audit License Server on Render + MongoDB

## MongoDB Atlas

1. Create a free MongoDB Atlas cluster.
2. Create a database user and password.
3. Allow network access from Render. For easiest setup, add `0.0.0.0/0`.
4. Copy the SRV connection string, for example:

```text
mongodb+srv://USER:PASSWORD@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority
```

## Render

1. Push this project to GitHub.
2. In Render, create a new **Web Service**.
3. Set the root directory to `server`.
4. Use:

```text
Build Command: pip install -r requirements.txt
Start Command: gunicorn app:app
```

5. Add environment variables:

```text
ADMIN_KEY=use-a-long-random-secret
MONGODB_URI=mongodb+srv://...
MONGODB_DB=bank_audit_licensing
```

6. Deploy. Your validation URL will be:

```text
https://YOUR-RENDER-APP.onrender.com/validate
```

## Desktop App

In `license_engine.py`, set:

```python
_SERVER_URL = "https://YOUR-RENDER-APP.onrender.com/validate"
_ADMIN_SERVER_KEY = "same-value-as-ADMIN_KEY"
```

Then rebuild the EXE.

## Endpoints

Client:

```text
POST /validate
```

Admin:

```text
POST /admin/register
POST /admin/extend
POST /admin/revoke
POST /admin/restore
GET  /admin/list
```

Admin endpoints require:

```text
X-Admin-Key: your ADMIN_KEY
```
