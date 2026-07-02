# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

FastAPI service ("TempoFTP" in the wider LANOT architecture) that provisions temporary FTP accounts (Pure-FTPd + MySQL) so clients can download recovered data over FTP for a limited validity period (`vigencia`, in days). Its primary (currently only) client is the Django app in the sibling repo `historic_query`, which creates a TempoFTP access after a data query completes and later reads back credentials/download stats — see that repo's `Query.aux.tempoftp` field for the contract shape. `README.md` documents the full HTTP API (all endpoints, request/response bodies, env vars) in detail — prefer it over re-deriving endpoint behavior from code. `ARQUITECTURA_REAL.md` describes the intended real-environment (non-simulated) deployment flow and checklist, though parts of it (e.g. the Celery mention) are aspirational, not what's implemented — trust `main.py`/`gestorftp.py` over that doc where they disagree.

## Commands

```bash
# Setup
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt      # or: pip install fastapi uvicorn cryptography aiomysql pytest httpx slowapi passlib argon2-cffi python-dotenv
export TEMPOFTP_ENCRYPTION_KEY=$(python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")

# Run (dev, simulated backend — no real MySQL/Pure-FTPd/rsync needed)
export TEMPOFTP_SIMULACRO=1
uvicorn main:app --reload --port 9043

# Run (real backend; worker count is no longer constrained by cleanup —
# see "Deployment" below — pick based on expected load, e.g. --workers 4)
export TEMPOFTP_SIMULACRO=0
uvicorn main:app --host 0.0.0.0 --port 9043 --workers 4

# Tests (TMPFTPdb uses ':memory:' automatically when PYTEST_CURRENT_TEST is set; get_gestor() defaults to the simulator under pytest unless TEMPOFTP_SIMULACRO is explicitly set)
pytest
pytest test_main.py::test_name        # single test
```

No linter configured; no CI workflow in this repo (unlike its sibling `historic_server`).

## Architecture

### Request lifecycle
`main.py` → `get_gestor()` (a `lru_cache`d dependency picking `GestorFTP` (real) or `GestorFTPsim` (simulated) based on `TEMPOFTP_SIMULACRO`/pytest context) → `create_usertmp()` does the actual provisioning → state persisted in `tmpftpdb.py`'s SQLite (`solicitudes` table, states: `recibido`/`preparando`/`traslado`/`listo`/`error`/`bloqueado`/`expirado`) → client polls `GET /tmpftp/{id}`.

`GestorFTPBase` (`gestorftpbase.py`) holds logic shared between real and simulated gestores: deterministic username generation (`ftp_<local>_<domain-label>` from the requester's email), password generation, and `get_status()` (reads `TMPFTPdb`, shapes the response). `GestorFTP` and `GestorFTPsim` both subclass it and are meant to be interchangeable from `main.py`'s perspective — when adding a new gestor method, add it to both (and to the base if the logic is truly shared).

### Real gestor (`gestorftp.py`)
- `FTPDB_MySQL` — thin `aiomysql` pool wrapper against Pure-FTPd's `users` table (User/Password/Uid/Gid/Dir/Status). Passwords are hashed with Argon2id (`PasswordHasher` from `argon2-cffi`) before insert/update — `main.py`'s `validate_pureftpd_config()` checks at startup that `pureftpd-mysql.conf`'s `MYSQLCrypt` is set to `argon2`, failing fast on mismatch (or warning + continuing if the conf file isn't readable).
- Provisioning flow (`create_usertmp`): validate `ruta_remota` format (`host:/path` or `user@host:/path`), get remote size via `du -sb` (over SSH unless `_es_host_local()` detects loopback/local), check free space in `/data` (`verificar_espacio_data`), `rsync -av` the data into `/data/{usuario}/{id}` (`_preparar_directorio` creates dirs, chowns to `DATA_OWNER_USER`/`DATA_OWNER_GROUP` unless `SKIP_CHOWN=1`), then create-or-update the MySQL FTP user. **Idempotent semantics**: if the FTP user already exists, its password is regenerated and updated (never left stale, never returned in plaintext from a prior run) rather than erroring.
- `obtener_estadisticas_descargas()` parses Pure-FTPd's CLF-style `transfer.log` (`/var/log/pure-ftpd/transfer.log`) to count download "sessions" (unique IP+day pairs) filtered to the specific `consulta_id` subdirectory — this is why moving/renaming a request's data directory would break download stats for past requests.
- `eliminar_expiradas()` purges expired `listo`/`bloqueado` requests (a blocked request still expires by its original `vigencia` — blocking only disables login early, it doesn't extend or cancel retention): deletes the `/data/{usuario}/{id}` subdir, marks SQLite `expirado`, and drops the MySQL FTP user entirely only if the user has no other active (non-terminal) requests (`obtener_activas_por_usuario`) — so one user's multiple concurrent requests share one FTP account safely. Invoked both by `DELETE /tmpftp/expired` (manual trigger) and by `cleanup_expired.py`, a standalone script run via a systemd timer (`deployment/tempoftp-cleanup.service`/`.timer`, default every 24h) — **not** an in-process loop. That's a deliberate fix (see `AUDITORIA_2026-07.md` P0-1): a loop tied to FastAPI's `lifespan` would run once per uvicorn worker, duplicating the cleanup (and its SQLite/MySQL writes) by the worker count.
- Directory deletion is guarded (`_borrar_directorio_seguro`) to only ever operate under `/data/`.

### Simulated gestor (`gestorftpsim.py`)
Used for local dev/tests (`TEMPOFTP_SIMULACRO=1`, or implicitly under pytest when `TEMPOFTP_SIMULACRO` is unset). No MySQL/rsync/SSH involved. `TEMPOFTP_SIM_FORCE` can force `ok`/`fail` outcomes; otherwise it evaluates simulated remote/free-space sizes (`TEMPOFTP_SIM_REMOTE_SIZE_BYTES`, `TEMPOFTP_SIM_DATA_FREE_BYTES`) to decide success/failure, mimicking the real gestor's space-check logic.

### Credentials handling
Plaintext FTP passwords are never persisted anywhere — `cifrado.py`'s `cifrar()` (Fernet, keyed by `TEMPOFTP_ENCRYPTION_KEY`) encrypts the password before it's stored in SQLite/returned over the API; `decodepw.py` and the reference client `apiclient.py` decrypt it client-side using the same key (must match between service and any consumer, i.e. `historic_query`). Blocking a request (`bloquear_solicitud`, `Status=0` in MySQL) doesn't delete the account or data — only `eliminar_expiradas`/explicit delete endpoints do that.

`TEMPOFTP_ENCRYPTION_KEY` is hard-required (see P0-2 in `AUDITORIA_2026-07.md`): `cifrado.py` raises `RuntimeError` at import time if it's missing, instead of silently generating a throwaway key — that used to mean every worker/restart got a different key, making previously-encrypted passwords permanently undecryptable. `main.py`'s `lifespan` calls `validate_encryption_key()` (which just imports `cifrado`) so this fails at startup, not on the first real `/tmpftp` request.

### Correlation IDs & logging
`X-Request-ID` is read from the incoming header or generated (`uuid4`), stored in a `ContextVar`, injected into every log line via a `logging.Filter` (`CorrelationIDFilter`), and echoed back in the response header — mirrors the pattern used in `historic_server` and `historic_query`, so a request can be traced across all three services by that header.

### Deployment
`deployment/` holds the systemd units for the API (`tempoftp.service`, `tempoftp-direct.service`), the cleanup timer (`tempoftp-cleanup.service`/`.timer`, running `cleanup_expired.py` — see above), nginx config, and `tempoftp.env.example` — see `deployment/Deployment.md`. Production must run Pure-FTPd + MySQL with `MYSQLCrypt=argon2` in `pureftpd-mysql.conf` to match `_hash_password()`; the `tools/` scripts (`crear_usuario_ftp.py`, `actualizar_password_ftp.py`, `diagnostico_usuario_ftp.py`, `ftp_admin.py`) are standalone ops helpers for inspecting/fixing the MySQL side directly, independent of the running API.
