"""Vaqtinchalik: POS JSON narxlarni HTTP orqali yuklash (scp o'rniga).

POST /api/catalog/restore-prices-upload/
Header: X-Restore-Secret: <RESTORE_PRICES_SECRET>
Body: raw JSON array (tezpos_products export)
Query: ?tenant=kuloloptom-2&apply=1
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from django.core.management import call_command
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

ALLOWED_TENANTS = frozenset({"kuloloptom-2"})


@csrf_exempt
@require_POST
def restore_prices_upload(request):
    expected = (os.environ.get("RESTORE_PRICES_SECRET") or "").strip()
    got = (request.headers.get("X-Restore-Secret") or "").strip()
    if not expected or got != expected:
        return JsonResponse({"ok": False, "error": "unauthorized"}, status=401)

    tenant = (request.GET.get("tenant") or "kuloloptom-2").strip()
    if tenant not in ALLOWED_TENANTS:
        return JsonResponse(
            {"ok": False, "error": f"tenant ruxsat etilmagan: {tenant}"},
            status=400,
        )

    body = request.body or b""
    if len(body) < 10:
        return JsonResponse({"ok": False, "error": "bo'sh body"}, status=400)
    if len(body) > 25_000_000:
        return JsonResponse({"ok": False, "error": "fayl juda katta"}, status=400)

    try:
        data = json.loads(body.decode("utf-8"))
    except Exception as exc:
        return JsonResponse({"ok": False, "error": f"JSON xato: {exc}"}, status=400)

    if not isinstance(data, list):
        return JsonResponse({"ok": False, "error": "JSON massiv bo'lishi kerak"}, status=400)

    out = Path("/tmp/products_kuloloptom-2.json")
    out.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    apply = (request.GET.get("apply") or "").strip() in ("1", "true", "yes")
    from io import StringIO

    buf = StringIO()
    try:
        if apply:
            call_command(
                "restore_prices_from_json",
                str(out),
                tenant=tenant,
                stdout=buf,
            )
        else:
            call_command(
                "restore_prices_from_json",
                str(out),
                tenant=tenant,
                dry_run=True,
                stdout=buf,
            )
    except Exception as exc:
        return JsonResponse(
            {"ok": False, "error": str(exc), "log": buf.getvalue()[-4000:]},
            status=500,
        )

    return JsonResponse(
        {
            "ok": True,
            "tenant": tenant,
            "apply": apply,
            "products_in_json": len(data),
            "saved_to": str(out),
            "log": buf.getvalue()[-6000:],
        }
    )
