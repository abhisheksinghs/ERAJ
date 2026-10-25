"""Which modules the current tenant has paid for.

Modules talk to each other in-process (ADR-003), so a module must check before
it relies on another one: a Basic-plan college with only Library must not get
library fines posted into a Fees ledger it cannot open.
"""
from django.db import connection
from django_tenants.utils import get_public_schema_name

from apps.core.middleware import get_subscription_state
from apps.core.models import Client


def tenant_has_module(code: str) -> bool:
    schema = getattr(connection, "schema_name", None)
    if not schema or schema == get_public_schema_name():
        return False
    tenant = getattr(connection, "tenant", None)
    if not isinstance(tenant, Client):  # schema_context() / Celery: a FakeTenant
        tenant = Client.objects.filter(schema_name=schema).first()
        if tenant is None:
            return False
    return code in get_subscription_state(tenant)["modules"]
