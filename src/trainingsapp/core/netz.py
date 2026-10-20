"""Gemeinsames für alles, was die App aus dem Netz holt (S8, Ben, 20.10.2026).

Zwei Stellen sprechen per `urllib` nach draußen: `core/update.py` (GitHub-Releases)
und `core/paketquelle.py` (Paketindex und -dateien). Beide gehen nur über
``https://`` — und sollen auch bei einer **Weiterleitung** nicht nach ``http://``
abbiegen, wie `urllib` es von sich aus täte (Katalog A9 bei den Quellen, S8 beim
Update). Darum wohnt der Öffner hier und nicht doppelt.

``http://`` zum eigenen Rechner (``localhost``, ``127.0.0.1``, ``[::1]``) bleibt
erlaubt — zum Ausprobieren mit ``python -m http.server``.

Dieses Modul kennt kein flet.
"""

from __future__ import annotations

import urllib.error
import urllib.request
from typing import Any

#: http:// nur zum eigenen Rechner
_LOKAL = ("http://localhost", "http://127.0.0.1", "http://[::1]")


def verschluesselt(url: str) -> bool:
    """``https://`` — oder ``http://`` zum eigenen Rechner.

    >>> verschluesselt("https://example.org/x"), verschluesselt("http://example.org/x")
    (True, False)
    >>> verschluesselt("http://localhost:8000/index.json"), verschluesselt("ftp://x")
    (True, False)
    """
    return url.startswith("https://") or url.startswith(_LOKAL)


class NurHttps(urllib.request.HTTPRedirectHandler):
    """Weiterleitungen nur auf https:// — `urllib` folgte sonst auch nach http://."""

    def redirect_request(
        self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str
    ) -> Any:
        if not verschluesselt(newurl):
            raise urllib.error.HTTPError(
                newurl, code, "Weiterleitung nur auf https://", headers, fp
            )
        return super().redirect_request(req, fp, code, msg, headers, newurl)


#: Der eine Öffner für Update-Prüfung und Paketquellen
OEFFNER = urllib.request.build_opener(NurHttps)


__all__ = ["OEFFNER", "NurHttps", "verschluesselt"]
