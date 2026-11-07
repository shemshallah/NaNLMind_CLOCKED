#!/bin/sh
set -eu

: "${CLOCKED_API_KEY:?CLOCKED_API_KEY must be configured in Koyeb secrets}"
: "${CLOCKED_GATEWAY_ADMIN_TOKEN:?CLOCKED_GATEWAY_ADMIN_TOKEN must be configured}"
: "${CLOCKED_DEMO_ENROLLMENT_TOKEN:?CLOCKED_DEMO_ENROLLMENT_TOKEN must be configured}"
: "${CLOCKED_TOKEN_PEPPER:?CLOCKED_TOKEN_PEPPER must be configured}"
: "${CLOCKED_RESULT_ENCRYPTION_KEY:?CLOCKED_RESULT_ENCRYPTION_KEY must be configured}"

python - <<'PY'
import os
from cryptography.fernet import Fernet
for name in ("CLOCKED_GATEWAY_ADMIN_TOKEN", "CLOCKED_DEMO_ENROLLMENT_TOKEN", "CLOCKED_TOKEN_PEPPER"):
    if len(os.environ[name]) < 32:
        raise SystemExit(name + " must contain at least 32 characters")
try:
    Fernet(os.environ["CLOCKED_RESULT_ENCRYPTION_KEY"].encode("ascii"))
except Exception as exc:
    raise SystemExit("CLOCKED_RESULT_ENCRYPTION_KEY must be a valid Fernet key") from exc
PY

mkdir -p "${CLOCKED_GATEWAY_DB%/*}"
exec gunicorn gateway:application \
    --bind "0.0.0.0:${PORT:-8080}" \
    --workers 1 \
    --threads 12 \
    --timeout 120 \
    --access-logfile - \
    --error-logfile -
