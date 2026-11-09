import math

from eisspeicher import (
    GEBAEUDESTANDARDS,
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


def test_nutzbar_pro_m3_mit_anfangsbeladung():
    a = Auslegung(wohnflaeche_m2=1000.0, anfangstemperatur=20.0, nutzungsgrad=1.0)
    sensibel = 1000.0 * 1.163 * 20.0 / 1000.0  # 23.26 kWh/m^3
    assert math.isclose(a.nutzbar_pro_m3_kwh, LATENT_WAERME + sensibel)


def test_cop_booster_aus_temperaturen():
    a = Auslegung(wohnflaeche_m2=1000.0,
                  netz_vorlauf_c=10.0, netz_ruecklauf_c=5.0,
                  heizung_vorlauf_c=35.0, guetegrad=0.5)
    assert math.isclose(a.quelle_c, 10.0)
    t_h, t_q = 35.0 + 273.15, 10.0 + 273.15
    assert math.isclose(a.cop_booster, 0.5 * t_h / (t_h - t_q))


def test_cop_booster_fest_vorgegeben():
    a = Auslegung(wohnflaeche_m2=1000.0, cop_mittel=3.2)
    assert a.cop_booster == 3.2


def test_cop_booster_ungueltig():
    a = Auslegung(wohnflaeche_m2=1000.0, heizung_vorlauf_c=5.0,
                  netz_vorlauf_c=6.0, netz_ruecklauf_c=12.0)
    try:
        _ = a.cop_booster
    except ValueError:
        return
    raise AssertionError("ValueError erwartet, wenn Heizungs-Vorlauf <= Netztemperatur")


def test_volumen_geometrie_und_lichte_hoehe():
    a = Auslegung(wohnflaeche_m2=40000.0, lichte_hoehe_m=3.0)
    assert math.isclose(
        a.volumen_m3,
        (a.winter_waermebedarf_kwh / a.cop_booster) / a.nutzbar_pro_m3_kwh,
    )
    assert math.isclose(a.grundflaeche_m2, a.volumen_m3 / 3.0)
    assert math.isclose(
        math.pi * (a.tank_durchmesser_m / 2) ** 2 * 3.0, a.volumen_m3
    )


def test_gebaeudestandards():
    assert GEBAEUDESTANDARDS["KfW EH40 / EH40-EE"] == 35.0
    assert all(v > 0 for v in GEBAEUDESTANDARDS.values())


def test_defaults_kaltes_netz():
    a = Auslegung(wohnflaeche_m2=1000.0)
    assert a.netz_vorlauf_c == 10.0
    assert a.netz_ruecklauf_c == 5.0
    assert math.isclose(a.quelle_c, 10.0)


def test_hysterese_und_volumenstrom():
    a = Auslegung(wohnflaeche_m2=40000.0, netz_vorlauf_c=10.0, netz_ruecklauf_c=5.0)
    assert math.isclose(a.hysterese_c, 5.0)
    assert math.isclose(a.energie_pro_m3_netz_kwh, 1000.0 * 1.163 * 5.0 / 1000.0)
    assert math.isclose(
        a.volumenstrom_netz_m3h,
        (a.quellenenergie_kwh / (TAGE_HEIZPERIODE * 24.0)) / a.energie_pro_m3_netz_kwh,
    )


def test_vorlauf_muss_hoeher_als_ruecklauf_sein():
    a = Auslegung(wohnflaeche_m2=1000.0, netz_vorlauf_c=5.0, netz_ruecklauf_c=10.0)
    try:
        _ = a.hysterese_c
    except ValueError:
        return
    raise AssertionError("ValueError erwartet, wenn Netz-VL <= Netz-RL")


def test_bericht_enthaelt_kernwerte():
    a = Auslegung(wohnflaeche_m2=40000.0)
    text = bericht(a)
    assert "40.000 m²" in text
    assert "m³" in text
    assert "COP Booster" in text
    assert "Lichte Höhe" in text
    assert "Hysterese" in text
