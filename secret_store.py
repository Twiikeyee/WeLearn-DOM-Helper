# -*- coding: utf-8 -*-
"""
Optional OS keychain storage for sensitive config fields (password / api_key).

Uses the `keyring` package when it is installed (macOS Keychain, Windows
Credential Manager, Secret Service on Linux). When `keyring` is missing or the
backend fails, every function degrades gracefully so callers can fall back to
plain-text storage in config.json.

Licensed under GNU AGPLv3.
"""

import logging
from typing import Optional

logger = logging.getLogger("WeLearnBot")

SERVICE_NAME = "WeLearn-DOM-Helper"
SECRET_KEYS = ("password", "api_key")

try:  # pragma: no cover - depends on environment
    import keyring as _keyring
    from keyring.errors import PasswordDeleteError as _PasswordDeleteError
except Exception:  # pragma: no cover
    _keyring = None
    _PasswordDeleteError = Exception


def is_available() -> bool:
    """Return True if a usable (non-fail) keyring backend exists."""
    if _keyring is None:
        return False
    try:
        backend = _keyring.get_keyring()
        return "fail" not in type(backend).__module__.lower()
    except Exception:
        return False


def get_secret(key: str) -> Optional[str]:
    if not is_available():
        return None
    try:
        return _keyring.get_password(SERVICE_NAME, key)
    except Exception as e:
        logger.debug("keyring get failed for %s: %s", key, e)
        return None


def set_secret(key: str, value: str) -> bool:
    """Store value; an empty value deletes the entry. Returns True on success."""
    if not is_available():
        return False
    try:
        if value:
            _keyring.set_password(SERVICE_NAME, key, value)
        else:
            try:
                _keyring.delete_password(SERVICE_NAME, key)
            except _PasswordDeleteError:
                pass
        return True
    except Exception as e:
        logger.debug("keyring set failed for %s: %s", key, e)
        return False
