from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from typing import Any

from ..exceptions import BadResponseError, NetworkError, ServerError, TimeoutError

USER_AGENT = "TezPOS/1.0 (POS; barcode lookup)"
DEFAULT_HTTP_TIMEOUT = 8.0


def http_get_json(url: str, *, timeout: float = DEFAULT_HTTP_TIMEOUT) -> Any:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        method="GET",
    )
    return _read_json_response(request, timeout)


def _read_json_response(request: urllib.request.Request, timeout: float) -> Any:
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        if exc.code >= 500:
            raise ServerError() from exc
        raise BadResponseError() from exc
    except urllib.error.URLError as exc:
        reason = exc.reason
        if isinstance(reason, (TimeoutError, socket.timeout)):
            raise TimeoutError() from exc
        raise NetworkError() from exc
    except TimeoutError as exc:
        raise TimeoutError() from exc
    except OSError as exc:
        if "timed out" in str(exc).lower():
            raise TimeoutError() from exc
        raise NetworkError() from exc

    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise BadResponseError() from exc
