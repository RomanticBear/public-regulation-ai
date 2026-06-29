"""Supabase 연결 후보 URL 탐색 (비밀번호는 .env 사용)."""

from __future__ import annotations

import os
import ssl
import sys
from pathlib import Path
from urllib.parse import quote, urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv()

import psycopg2

DB_HOST_V6 = "2406:da12:557:f800:85b2:5247:ce55:196b"
PROJECT = "emjypaorpmitjhemmvyh"
REGIONS = [
    "ap-northeast-2",
    "ap-northeast-1",
    "us-east-1",
    "us-west-1",
    "eu-west-1",
    "eu-central-1",
    "ap-southeast-1",
]


def connect(host: str, port: int, user: str, password: str, dbname: str = "postgres"):
    ssl_verify = os.getenv("DATABASE_SSL_VERIFY", "true").lower() not in (
        "0",
        "false",
        "no",
    )
    kwargs: dict = {
        "host": host,
        "port": port,
        "user": user,
        "password": password,
        "dbname": dbname,
        "sslmode": "require",
    }
    if not ssl_verify:
        kwargs["sslrootcert"] = None
    return psycopg2.connect(**kwargs)


def main() -> None:
    password = os.getenv("DATABASE_URL", "")
    parsed = urlparse(password if password.startswith("postgresql") else "")
    password = parsed.password or os.getenv("SUPABASE_DB_PASSWORD", "")
    if not password:
        print("password missing in DATABASE_URL")
        sys.exit(1)

    candidates: list[tuple[str, str, int, str]] = []

    candidates.append(("direct-ipv6", f"[{DB_HOST_V6}]", 5432, "postgres"))
    for prefix in ("aws-0", "aws-1"):
        for region in REGIONS:
            host = f"{prefix}-{region}.pooler.supabase.com"
            for port in (5432, 6543):
                candidates.append((f"pooler-{prefix}-{region}-{port}", host, port, f"postgres.{PROJECT}"))
                candidates.append((f"pooler-{prefix}-{region}-{port}-plain", host, port, "postgres"))

    for label, host, port, user in candidates:
        try:
            conn = connect(host.strip("[]"), port, user, password)
            cur = conn.cursor()
            cur.execute("SELECT 1")
            cur.fetchone()
            conn.close()
            print(f"OK {label} host={host} port={port} user={user}")
            if host.startswith("["):
                url = f"postgresql://{quote(user, safe='')}:{quote(password, safe='')}@{host}:{port}/postgres?sslmode=require"
            else:
                url = f"postgresql://{quote(user, safe='')}:{quote(password, safe='')}@{host}:{port}/postgres?sslmode=require"
            print("DATABASE_URL=" + url)
            return
        except Exception as exc:
            msg = str(exc).replace("\n", " ")[:100]
            print(f"FAIL {label}: {msg}")

    sys.exit(1)


if __name__ == "__main__":
    main()
