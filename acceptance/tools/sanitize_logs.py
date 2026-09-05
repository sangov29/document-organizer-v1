from __future__ import annotations

import re
import sys
from pathlib import Path

JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")
TOKEN_QUERY_RE = re.compile(r"([?&]token=)[^&\s]+", re.I)
BEARER_RE = re.compile(r"(Bearer\s+)[A-Za-z0-9._~-]+", re.I)
KEY_VALUE_RE = re.compile(r"(?i)\b(password|new_password|jwt_secret|totp_fernet_key|totp_secret|secret|access_token)=([^\s]+)")
PROVISION_RE = re.compile(r"otpauth://[^\s]+", re.I)


def sanitize(text: str) -> str:
    text = JWT_RE.sub("<redacted-jwt>", text)
    text = TOKEN_QUERY_RE.sub(r"\1<redacted>", text)
    text = BEARER_RE.sub(r"\1<redacted>", text)
    text = KEY_VALUE_RE.sub(lambda m: f"{m.group(1)}=<redacted>", text)
    text = PROVISION_RE.sub("<redacted-otpauth-uri>", text)
    return text


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: sanitize_logs.py INPUT OUTPUT", file=sys.stderr)
        return 2
    source, target = Path(sys.argv[1]), Path(sys.argv[2])
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(sanitize(source.read_text(errors="replace")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
