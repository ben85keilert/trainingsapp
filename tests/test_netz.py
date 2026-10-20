"""`core/netz.py` (S8): der gemeinsame Öffner folgt Weiterleitungen nur auf https://."""

from __future__ import annotations

import email.message
import urllib.error
import urllib.request

import pytest

from trainingsapp.core import netz, paketquelle, update


def _weiterleitung(ziel: str, code: int = 302):
    handler = netz.NurHttps()
    anfrage = urllib.request.Request("https://api.github.com/repos/x/releases")
    return handler.redirect_request(anfrage, None, code, "Found", email.message.Message(), ziel)


def test_weiterleitung_nur_auf_https() -> None:
    neu = _weiterleitung("https://objects.example.org/d.json")
    assert neu is not None and neu.full_url == "https://objects.example.org/d.json"
    for ziel in ("http://objects.example.org/d.json", "ftp://x/d", "file:///etc/passwd"):
        with pytest.raises(urllib.error.HTTPError, match="nur auf https"):
            _weiterleitung(ziel)
    # http:// zum eigenen Rechner bleibt — zum Ausprobieren mit `python -m http.server`
    assert _weiterleitung("http://localhost:8000/i.json", 301) is not None


def test_update_und_paketquelle_teilen_den_oeffner() -> None:
    """Keine zweite Öffnerklasse — beide Module gehen über `netz.OEFFNER`."""
    assert update.OEFFNER is netz.OEFFNER and paketquelle.OEFFNER is netz.OEFFNER
    assert any(isinstance(h, netz.NurHttps) for h in netz.OEFFNER.handlers)
    assert not any(type(h) is urllib.request.HTTPRedirectHandler for h in netz.OEFFNER.handlers)
