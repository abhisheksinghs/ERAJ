"""Which modules the current tenant has paid for.

Modules talk to each other in-process (ADR-003), so a module must check before
it relies on another one: a Basic-plan college with only Library must not get
library fines posted into a Fees ledger it cannot open.
"""
from django.db import connection
from django_tenants.utils import get_public_schema_name

from apps.core.middleware import get_subscription_state


def tenant_has_module(code: str) -> bool:
    tenant = getattr(connection, "tenant", None)
    if tenant is None or tenant.schema_name == get_public_schema_name():
        return False
    return code in get_subscription_state(tenant)["modules"]
