"""Liveness + readiness probes, shared by the tenant and public URLconfs."""
from django.core.cache import cache
from django.db import connection
from django.http import JsonResponse


def live(request):
    """Liveness: the process is up. No dependency checks — a failing DB must
    not cause the orchestrator to kill an otherwise-healthy container."""
    return JsonResponse({"status": "ok"})


def ready(request):
    """Readiness: DB + cache reachable. Gate rollouts / load-balancer on this."""
    try:
        connection.ensure_connection()
        cache.set("_health", "1", timeout=5)
        if cache.get("_health") != "1":
            raise RuntimeError("cache round-trip failed")
    except Exception as exc:  # noqa: BLE001 - any failure here means "not ready"
        return JsonResponse({"status": "not_ready", "error": str(exc)}, status=503)
    return JsonResponse({"status": "ready"})
