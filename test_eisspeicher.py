import math

from eisspeicher import (
    Auslegung,
    LATENT_WAERME,
    TAGE_HEIZPERIODE,
    bericht,
)


def test_jahreswerte():
    a = Auslegung(wohnflaeche_m2=40000.0)
    assert a.jahres_raumwaerme_kwh == 40000.0 * 35.0
    assert a.jahres_trinkwarm_kwh == 40000.0 * 12.5


def test_winteranteil_und_waermebedarf():
    a = Auslegung(wohnflaeche_m2=40000.0)
    assert math.isclose(sum(a.monate.values()), 1.0)
    raum = a.jahres_raumwaerme_kwh
    warm = a.jahres_trinkwarm_kwh * TAGE_HEIZPERIODE / 365.0
    assert math.isclose(a.winter_waermebedarf_kwh, raum + warm)


def test_nutzbar_pro_m3():
    a = Auslegung(wohnflaeche_m2=1000.0, starttemperatur=10.0, nutzungsgrad=1.0)
    sensibel = 1000.0 * 1.163 * 10.0 / 1000.0  # 11.63 kWh/m^3
    assert math.isclose(a.nutzbar_pro_m3_kwh, LATENT_WAERME + sensibel)


def test_volumen_und_tankgeometrie():
    a = Auslegung(wohnflaeche_m2=40000.0)
    assert math.isclose(
        a.volumen_m3,
        (a.winter_waermebedarf_kwh / a.cop_mittel) / a.nutzbar_pro_m3_kwh,
    )
    d = a.tank_durchmesser(3.0)
    assert math.isclose(math.pi * (d / 2) ** 2 * 3.0, a.volumen_m3)
    assert a.volumen_m3 > 0


def test_bericht_enthaelt_kernwerte():
    a = Auslegung(wohnflaeche_m2=40000.0)
    text = bericht(a, 3.0)
    assert "40.000 m²" in text
    assert "m³" in text
