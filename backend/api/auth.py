"""
Shared-secret API key auth. If APP_API_KEY is unset, auth is skipped
(keeps local dev frictionless) - set it before deploying anywhere public.
"""

import os
from fastapi import Header, HTTPException


def require_api_key(x_api_key: str | None = Header(default=None)):
    expected = os.getenv("APP_API_KEY")
    if not expected:
        return
    if x_api_key != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing API key.")
