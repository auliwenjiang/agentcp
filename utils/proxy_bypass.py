# -*- coding: utf-8 -*-
import os
from contextlib import contextmanager
from urllib.parse import urlparse


_LOCAL_HOSTS = ("localhost", "127.0.0.1", "::1", "0.0.0.0")
_LOCAL_NO_PROXY = "localhost,127.0.0.1,::1"
LOCAL_NO_PROXY_LIST = ["localhost", "127.0.0.1", "::1"]


def ensure_no_proxy_for_local_env() -> None:
    """Ensure NO_PROXY/no_proxy includes localhost, as a safety net against global proxies."""
    for key in ("NO_PROXY", "no_proxy"):
        existing = (os.environ.get(key) or "").strip()
        if not existing:
            os.environ[key] = _LOCAL_NO_PROXY
            continue

        existing_parts = [p.strip() for p in existing.replace(";", ",").split(",") if p.strip()]
        existing_lower = {p.lower() for p in existing_parts}
        for host in _LOCAL_NO_PROXY.split(","):
            if host.lower() not in existing_lower:
                existing_parts.append(host)
        os.environ[key] = ",".join(existing_parts)


def is_local_url(url: str) -> bool:
    """Return True when URL hostname is localhost/loopback."""
    try:
        parsed = urlparse(url)
        host = parsed.hostname
        if not host:
            return False
        host = host.strip("[]").lower()
        return host in _LOCAL_HOSTS
    except Exception:
        return False


def get_requests_proxies(use_system_proxy: bool, url: str):
    """
    For requests:
      - {} disables proxy
      - None uses env/system proxy
    """
    return {}


def get_trust_env(use_system_proxy: bool, url: str) -> bool:
    """For httpx/aiohttp trust_env: never trust env proxy for any URL."""
    return False


def pop_proxy_env():
    """Remove proxy env vars and return the saved mapping for restoration."""
    keys = (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "FTP_PROXY",
        "SOCKS_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
        "ftp_proxy",
        "socks_proxy",
    )
    saved = {k: os.environ.get(k) for k in keys}
    for k in keys:
        os.environ.pop(k, None)
    return saved


def restore_proxy_env(saved) -> None:
    if not saved:
        return
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


@contextmanager
def without_proxy_env(enabled: bool = True):
    """
    Temporarily remove proxy env vars (HTTP(S)_PROXY/ALL_PROXY and lowercase variants).
    Useful for websocket libraries that consult env proxies.
    """
    if not enabled:
        yield
        return

    saved = pop_proxy_env()
    try:
        yield
    finally:
        restore_proxy_env(saved)
