"""Fail fast on unsafe production configuration.

Imported by settings.py right after DEBUG/SECRET_KEY are resolved. Kept as a
pure function (no module-level Django import) so it is trivially self-checkable
with `python config/env_guard.py`.
"""
from __future__ import annotations

INSECURE_SECRET = "dev-insecure-key-change-in-production"


def check_production_safety(*, is_production: bool, debug: bool, secret_key: str) -> None:
    """Raise if a staging/prod process is running with dev-grade settings."""
    if not is_production:
        return
    problems = []
    if debug:
        problems.append("DEBUG must be False in production")
    if secret_key == INSECURE_SECRET or len(secret_key) < 50:
        problems.append("DJANGO_SECRET_KEY must be a unique value of 50+ characters")
    if problems:
        from django.core.exceptions import ImproperlyConfigured

        raise ImproperlyConfigured("Unsafe production configuration: " + "; ".join(problems))


if __name__ == "__main__":
    _rejected = False
    try:
        check_production_safety(is_production=True, debug=True, secret_key="x" * 60)
    except Exception:
        _rejected = True
    assert _rejected, "prod + DEBUG=True must be rejected"

    _rejected = False
    try:
        check_production_safety(is_production=True, debug=False, secret_key=INSECURE_SECRET)
    except Exception:
        _rejected = True
    assert _rejected, "prod + sentinel secret must be rejected"

    # These must NOT raise.
    check_production_safety(is_production=True, debug=False, secret_key="a-real-" + "x" * 50)
    check_production_safety(is_production=False, debug=True, secret_key="short")
    print("env_guard self-check passed")
