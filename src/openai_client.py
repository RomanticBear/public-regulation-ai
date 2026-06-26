"""OpenAI 클라이언트 (회사망 SSL 프록시 대응)."""

from __future__ import annotations

import os

import httpx
from openai import OpenAI


def _ssl_verify_enabled() -> bool:
    return os.getenv("OPENAI_SSL_VERIFY", "true").lower() not in ("0", "false", "no")


def get_openai_client() -> OpenAI:
    if _ssl_verify_enabled():
        return OpenAI()
    return OpenAI(http_client=httpx.Client(verify=False))
