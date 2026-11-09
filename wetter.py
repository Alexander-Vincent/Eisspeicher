#!/usr/bin/env python3
"""Wetterdaten-Modul: PLZ -> nächste DWD-Station -> Zeitreihe + TRY-Datenbank.

Ablauf:
1. PLZ wird gegen eine PLZ-Koordinaten-Datei aufgelöst (Sample im Repo;
   für produktiven Einsatz vollständige Datei als plz_de.csv nachladen).
2. Nächste DWD-Klimastation wird per Haversine bestimmt (Sample-Stationsliste).
3. Letzte 3 Jahre: Stundenwerte Lufttemperatur (TU) live vom DWD CDC.
4. Ausblick: lokale SQLite-Datenbank mit TRY-Stundenwerten (DWD-TRY, falls
   erreichbar, sonst deterministisch synthetischer Fallback, klar markiert).

CLI:  python3 wetter.py <PLZ>
"""

from __future__ import annotations

import csv
import io
import math
import os
import re
import sqlite3
import sys
import urllib.request
import zipfile
from datetime import datetime, timedelta

DWD_CDC = "https://opendata.dwd.de/climate_environment/CDC"
TU_RECENT_URL = (
    DWD_CDC + "/observations_germany/climate/hourly/air_temperature/recent/"
    "stundenwerte_TU_{sid:05d}_akt.zip"
)
# TRY-Quelle konfigurierbar; exakter DWD-Pfad je TRY-Version/Klimazone
TRY_QUELLE_URL = DWD_CDC + "/derived_germany/TRY/"

HIER = os.path.dirname(os.path.abspath(__file__))
PLZ_DATEI = os.path.join(HIER, "plz_de.csv")       # optional: vollständige Datei
PLZ_SAMPLE = os.path.join(HIER, "plz_de_sample.csv")
STATIONEN_DATEI = os.path.join(HIER, "dwd_stationen.csv")
STATIONEN_SAMPLE = os.path.join(HIER, "dwd_stationen_sample.csv")
DB_PFAD = os.path.join(HIER, "wetter.db")

PLZ_RE = re.compile(r"^\d{5}$")
HEIZGRENZE_C = 15.0
INNENTEMP_C = 20.0


class WetterFehler(Exception):
    pass


def plz_validieren(plz: str) -> bool:
    return bool(PLZ_RE.match(plz.strip())) and 1000 <= int(plz) <= 99999


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _lade_csv(pfad: str) -> list[dict]:
    with open(pfad, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def lade_plz_daten() -> dict[str, tuple[str, float, float]]:
    pfad = PLZ_DATEI if os.path.exists(PLZ_DATEI) else PLZ_SAMPLE
    return {r["plz"]: (r["ort"], float(r["lat"]), float(r["lon"]))
            for r in _lade_csv(pfad)}


def lade_stationen() -> list[dict]:
    pfad = STATIONEN_DATEI if os.path.exists(STATIONEN_DATEI) else STATIONEN_SAMPLE
    return [
        {"id": int(r["station_id"]), "name": r["name"],
         "lat": float(r["lat"]), "lon": float(r["lon"])}
        for r in _lade_csv(pfad)
    ]


def station_fuer_plz(plz: str) -> tuple[dict, str]:
    if not plz_validieren(plz):
        raise WetterFehler(f"Ungültige PLZ: {plz!r} (5 Ziffern erwartet)")
    plz = plz.strip()
    daten = lade_plz_daten()
    if plz not in daten:
        raise WetterFehler(
            f"PLZ {plz} nicht in der PLZ-Datei – bitte plz_de.csv mit "
            "vollständigen Daten (z. B. open-plz.de) ergänzen"
        )
    ort, lat, lon = daten[plz]
    stationen = lade_stationen()
    naechste = min(
        stationen,
        key=lambda s: haversine_km(lat, lon, s["lat"], s["lon"]),
    )
    return naechste, ort


def lade_dwd_letzte_3_jahre(sid: int, jahre: int = 3,
                            heute: datetime | None = None) -> list[tuple[datetime, float]]:
    """Stundenwerte Lufttemperatur (TT_TU) der letzten `jahre` Kalenderjahre."""
    heute = heute or datetime.now()
    jahr_min = heute.year - (jahre - 1)
    url = TU_RECENT_URL.format(sid=sid)
    try:
        with urllib.request.urlopen(url, timeout=60) as r:
            data = r.read()
        zf = zipfile.ZipFile(io.BytesIO(data))
        name = next(n for n in zf.namelist() if n.startswith("produkt_tu_stunde"))
        text = zf.read(name).decode("latin-1")
    except Exception as e:
        raise WetterFehler(f"DWD-Download fehlgeschlagen ({url}): {e}") from e
    werte = []
    for line in text.splitlines()[1:]:
        parts = line.split(";")
        if len(parts) < 4:
            continue
        mess_datum, tt_tu = parts[1].strip(), parts[3].strip()
        try:
            t = float(tt_tu) / 10.0
            dt = datetime.strptime(mess_datum, "%Y%m%d%H")
        except ValueError:
            continue
        if t != -999.0 and dt.year >= jahr_min:
            werte.append((dt, t))
    if not werte:
        raise WetterFehler("Keine verwertbaren Stundenwerte vom DWD erhalten")
    return werte


def gradtage(werte: list[tuple[datetime, float]],
             innen: float = INNENTEMP_C, heizgrenze: float = HEIZGRENZE_C) -> float:
    gt = 0.0
    for _, t in werte:
        if t < heizgrenze:
            gt += (innen - t) / 24.0
    return gt


def monatsmittel(werte: list[tuple[datetime, float]]) -> list[float | None]:
    summen = [0.0] * 12
    anzahl = [0] * 12
    for dt, t in werte:
        summen[dt.month - 1] += t
        anzahl[dt.month - 1] += 1
    return [round(summen[m] / anzahl[m], 1) if anzahl[m] else None for m in range(12)]


def synthetischer_try(sid: int) -> list[tuple[datetime, float]]:
    """Deterministischer, klar als Fallback markierter TRY-Jahresgang (8760 h)."""
    basis = datetime(2010, 1, 1)
    werte = []
    for h in range(8760):
        tag = h // 24
        stunde = h % 24
        t = (9.5 + 8.5 * math.sin(2 * math.pi * (tag - 100) / 365.0)
             + 4.0 * math.sin(2 * math.pi * (stunde - 9) / 24.0)
             + 1.5 * math.sin(h * 12.9898 + sid))
        werte.append((basis + timedelta(days=tag, hours=stunde), round(t, 1)))
    return werte


def lade_try_vom_dwd(sid: int) -> list[tuple[datetime, float]]:
    """TRY-Stundenwerte vom DWD laden; TRY_QUELLE_URL je Klimazone konfigurieren."""
    url = TRY_QUELLE_URL + f"TRY_{sid:05d}.txt"
    try:
        with urllib.request.urlopen(url, timeout=60) as r:
            text = r.read().decode("latin-1")
    except Exception as e:
        raise WetterFehler(f"TRY-Download fehlgeschlagen: {e}") from e
    werte = []
    for line in text.splitlines():
        parts = line.split(";")
        if len(parts) < 2:
            continue
        try:
            dt = datetime.strptime(parts[0].strip(), "%Y%m%d%H")
            t = float(parts[1].strip().replace(",", "."))
        except ValueError:
            continue
        werte.append((dt, t))
    if len(werte) != 8760:
        raise WetterFehler(f"TRY unvollständig: {len(werte)} statt 8760 Stunden")
    return werte


def try_datenbank_erstellen(db_pfad: str, sid: int) -> tuple[int, str]:
    """SQLite-Datenbank mit TRY-Stundenwerten aufbauen; Quelle wird vermerkt."""
    try:
        werte = lade_try_vom_dwd(sid)
        quelle = "DWD TRY (live)"
    except WetterFehler:
        werte = synthetischer_try(sid)
        quelle = "synthetisch (Offline-Fallback)"
    conn = sqlite3.connect(db_pfad)
    with conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS try_stundenwerte ("
            "station_id INTEGER, zeitstempel TEXT, temperatur_c REAL, quelle TEXT)"
        )
        conn.execute("DELETE FROM try_stundenwerte WHERE station_id = ?", (sid,))
        conn.executemany(
            "INSERT INTO try_stundenwerte VALUES (?, ?, ?, ?)",
            [(sid, dt.isoformat(), t, quelle) for dt, t in werte],
        )
    conn.close()
    return len(werte), quelle


def wetter_bericht(plz: str, db_pfad: str = DB_PFAD) -> str:
    station, ort = station_fuer_plz(plz)
    zeilen = [
        f"=== Wetterdaten für PLZ {plz.strip()} ===",
        f"Ort (PLZ-Datei):                {ort}",
        f"Nächste DWD-Station:            {station['name']} (ID {station['id']:05d}, "
        f"{station['lat']:.3f}, {station['lon']:.3f})",
    ]
    try:
        werte = lade_dwd_letzte_3_jahre(station["id"])
        gt = gradtage(werte)
        zeilen += [
            f"Letzte 3 Jahre:                 DWD CDC live, {len(werte)} Stundenwerte",
            f"Gradtage (20/15 °C), gesamt:    {gt:,.0f} Kd",
        ]
    except WetterFehler as e:
        zeilen.append(f"Letzte 3 Jahre:                 nicht abrufbar ({e})")
    n, quelle = try_datenbank_erstellen(db_pfad, station["id"])
    zeilen += [
        f"TRY-Datenbank:                  {os.path.basename(db_pfad)}, {n} Stunden, Quelle: {quelle}",
        "Monatsmittel TRY (Temperatur):  "
        + " ".join(f"{m or 0.0:.1f}" for m in monatsmittel(synthetischer_try(station["id"]))),
    ]
    return "\n".join(zeilen)


def main() -> None:
    if len(sys.argv) != 2:
        print("Aufruf: python3 wetter.py <PLZ>")
        sys.exit(2)
    try:
        print(wetter_bericht(sys.argv[1]))
    except WetterFehler as e:
        print(f"Fehler: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
