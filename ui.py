#!/usr/bin/env python3
"""Web-UI zur Eisspeicher-Auslegung (nur Python-Standardbibliothek).

Start:  python3 ui.py [port]     ->  http://localhost:8000
Alle Eingabefelder sind Pflichtfelder.
"""

from __future__ import annotations

import html
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from eisspeicher import Auslegung, bericht

FELDER = [
    ("wohnflaeche_m2", "Beheizte Wohnfläche", "m²", "40000", "1"),
    ("heizwaermebedarf", "Heizwärmebedarf (z. B. KfW EH40-EE)", "kWh/(m²·a)", "35", "0.1"),
    ("trinkwarmwasser", "Trinkwarmwasser", "kWh/(m²·a)", "12.5", "0.1"),
    ("anfangstemperatur", "Beladung des Speichers zu Beginn der Heizperiode", "°C", "20", "0.5"),
    ("lichte_hoehe_m", "Lichte Höhe des Speichers", "m", "3", "0.1"),
    ("nutzungsgrad", "Nutzungsgrad des Speichers", "0–1", "0.9", "0.05"),
    ("netz_vorlauf_c", "Kaltes Wärmenetz – Vorlauftemperatur", "°C", "6", "0.5"),
    ("netz_ruecklauf_c", "Kaltes Wärmenetz – Rücklauftemperatur", "°C", "12", "0.5"),
    ("heizung_vorlauf_c", "Vorlauftemperatur Gebäudeheizung (Booster-Ziel)", "°C", "35", "1"),
    ("guetegrad", "Gütegrad der Booster-Wärmepumpen", "0–1", "0.5", "0.05"),
]

STYLE = """
body { font-family: sans-serif; max-width: 720px; margin: 2em auto; padding: 0 1em; }
h1 { font-size: 1.4em; }
label { display: block; margin-top: 0.9em; font-weight: bold; }
input { width: 12em; padding: 0.3em; }
.einheit { color: #666; margin-left: 0.4em; }
button { margin-top: 1.2em; padding: 0.5em 1.5em; font-size: 1em; }
pre { background: #f4f4f4; padding: 1em; border-radius: 6px; overflow-x: auto; }
.fehler { color: #b00; font-weight: bold; }
"""


def formular(werte: dict | None = None, fehler: str | None = None) -> str:
    werte = werte or {}
    felder = []
    for name, label, einheit, default, step in FELDER:
        value = werte.get(name, default)
        felder.append(
            f'<label for="{name}">{html.escape(label)}</label>'
            f'<input id="{name}" name="{name}" type="number" step="{step}" '
            f'value="{html.escape(str(value))}" required>'
            f'<span class="einheit">{html.escape(einheit)}</span>'
        )
    fehler_html = f'<p class="fehler">{html.escape(fehler)}</p>' if fehler else ""
    return f"""<!DOCTYPE html>
<html lang="de">
<head><meta charset="utf-8"><title>Eisspeicher-Auslegung</title>
<style>{STYLE}</style></head>
<body>
<h1>Eisspeicher-Auslegung (eine Heizperiode, ohne Regeneration)</h1>
{fehler_html}
<form method="get" action="/">
{''.join(felder)}
<button type="submit">Berechnen</button>
</form>
</body>
</html>"""


def ergebnis_seite(a: Auslegung) -> str:
    return f"""<!DOCTYPE html>
<html lang="de">
<head><meta charset="utf-8"><title>Eisspeicher – Ergebnis</title>
<style>{STYLE}</style></head>
<body>
<h1>Ergebnis</h1>
<pre>{html.escape(bericht(a))}</pre>
<p><a href="/">Neue Berechnung</a></p>
</body>
</html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        query = parse_qs(urlparse(self.path).query)
        if not query:
            self._senden(formular())
            return
        try:
            werte = {name: float(query[name][0]) for name, *_ in FELDER}
            a = Auslegung(**werte)
            self._senden(ergebnis_seite(a))
        except (KeyError, ValueError) as e:
            self._senden(formular({k: v[0] for k, v in query.items()}, str(e)))

    def _senden(self, inhalt: str) -> None:
        data = inhalt.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args) -> None:
        pass


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    server = HTTPServer(("127.0.0.1", port), Handler)
    print(f"UI läuft auf http://localhost:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
