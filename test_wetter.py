import math
import os
import sqlite3
import tempfile

import wetter


def test_plz_validierung():
    assert wetter.plz_validieren("10115")
    assert wetter.plz_validieren(" 80331 ")
    assert not wetter.plz_validieren("1234")
    assert not wetter.plz_validieren("abcde")
    assert not wetter.plz_validieren("00000")


def test_haversine():
    # Berlin -> Hamburg ca. 255 km
    d = wetter.haversine_km(52.52, 13.405, 53.551, 9.994)
    assert 230 < d < 280


def test_station_fuer_plz():
    station, ort = wetter.station_fuer_plz("10115")
    assert ort == "Berlin"
    assert "Berlin" in station["name"]
    try:
        wetter.station_fuer_plz("99999")
    except wetter.WetterFehler:
        return
    raise AssertionError("unbekannte PLZ muss WetterFehler werfen")


def test_gradtage_und_monatsmittel():
    from datetime import datetime, timedelta
    basis = datetime(2023, 1, 1)
    werte = [(basis + timedelta(hours=h), 10.0) for h in range(24 * 365)]
    assert math.isclose(wetter.gradtage(werte), (20.0 - 10.0) * 365)
    basis2 = datetime(2023, 6, 1)
    werte_kalt = [(basis2 + timedelta(hours=h), 25.0) for h in range(24 * 30)]
    assert wetter.gradtage(werte_kalt) == 0.0
    mm = wetter.monatsmittel(werte)
    assert len(mm) == 12
    assert all(m == 10.0 for m in mm)


def test_synthetischer_try_und_datenbank():
    werte = wetter.synthetischer_try(10382)
    assert len(werte) == 8760
    assert all(-30 < t < 45 for _, t in werte)
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, "wetter.db")
        n, quelle = wetter.try_datenbank_erstellen(db, 10382)
        assert n == 8760
        assert "synthetisch" in quelle or "DWD" in quelle
        conn = sqlite3.connect(db)
        count = conn.execute(
            "SELECT COUNT(*) FROM try_stundenwerte WHERE station_id = 10382"
        ).fetchone()[0]
        conn.close()
        assert count == 8760


def test_wetter_bericht_offline_fallback():
    text = wetter.wetter_bericht("10115", db_pfad=os.path.join(
        tempfile.mkdtemp(), "wetter.db"))
    assert "PLZ 10115" in text
    assert "Berlin" in text
    assert "TRY-Datenbank" in text
