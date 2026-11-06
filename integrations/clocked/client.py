#!/usr/bin/env python3
"""Hardware-neutral participant client; needs only Python's standard library."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


def endpoint_from_env() -> str:
    endpoint = os.environ.get("CLOCKED_INTAKE_URL", "").strip()
    if not endpoint:
        raise ValueError("CLOCKED_INTAKE_URL is required")
    parsed = urlparse(endpoint)
    if parsed.scheme not in ("https", "http") or not parsed.netloc:
        raise ValueError("CLOCKED_INTAKE_URL must be an HTTP(S) endpoint")
    if parsed.scheme != "https" and parsed.hostname not in ("localhost", "127.0.0.1", "::1"):
        raise ValueError("HTTPS is required except for localhost")
    return endpoint


def make_request(endpoint: str, token: str, text: str) -> Request:
    if not token or len(token) > 512:
        raise ValueError("CLOCKED_USER_API is missing or invalid")
    if not text.strip():
        raise ValueError("input text is empty")
    body = json.dumps({
        "protocol": "nanlm.clocked-experience",
        "text": text,
    }, ensure_ascii=False).encode("utf-8")
    return Request(
        endpoint,
        data=body,
        headers={
            "Authorization": "Bearer " + token,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="UTF-8 text file to submit to the demo gateway")
    args = parser.parse_args(argv)
    token = os.environ.get("CLOCKED_USER_API", "")
    try:
        endpoint = endpoint_from_env()
        text = args.input.read_text(encoding="utf-8")
        request = make_request(endpoint, token, text)
        with urlopen(request, timeout=60) as response:
            result = json.loads(response.read().decode("utf-8"))
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except HTTPError as exc:
        print("Demo gateway rejected the request (HTTP %d)." % exc.code, file=sys.stderr)
        return 1
    except (URLError, OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        print("Demo client failed (%s)." % type(exc).__name__, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
