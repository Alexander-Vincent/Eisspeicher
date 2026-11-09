#!/usr/bin/env python3
"""Auslegung eines Eisspeichers (Wärmequellen-Speicher für Wärmepumpen).

Sizing only: dimensioniert das Wasservolumen, das nötig ist, um eine
Heizperiode ohne Zwischenregeneration allein aus dem Eisspeicher zu
bedienen. Die Gebäude werden nicht direkt beheizt, sondern über ein
kaltes Wärmenetz mit Booster-Wärmepumpen; der COP der Booster wird aus
Netz- und Heizungs-Vorlauftemperatur abgeschätzt.

Eine zeitliche Simulation (Regeneration, Solarabsorber, Lastprofile)
ist als nächster Schritt vorgesehen.
"""

from __future__ import annotations

import argparse
import math
from dataclasses import dataclass, field

RHO_WASSER = 1000.0          # kg/m^3
C_WASSER = 1.163              # Wh/(kg*K)
LATENT_WAERME = 92.78         # kWh/m^3 (Gefrierwärme von Wasser, 334 kJ/kg)

# Heizwärmebedarf KfW EH40-EE: typisch 25-40 kWh/(m^2*a), Planung 35
DEFAULT_HEIZWAERMEBEDARF = 35.0   # kWh/(m^2*a) Raumwärme
DEFAULT_TRINKWARM = 12.5          # kWh/(m^2*a) nach DIN V 4701-10 (passend zu EH40)

# Gebäudetypologie: Standard -> mittlerer Heizwärmebedarf in kWh/(m^2*a)
GEBAEUDESTANDARDS = {
    "KfW EH40 / EH40-EE": 35.0,
    "KfW EH55 / EH55-EE": 45.0,
    "Neubau nach GEG": 55.0,
    "KfW EH70": 65.0,
    "Bestand teilsaniert": 100.0,
    "Bestand unsaniert": 150.0,
}

# Monatliche Verteilung des Raumwärmebedarfs (Anteile an der Jahresraumwärme)
HEIZPERIODE_MONATE = {
    "Oktober": 0.08,
    "November": 0.145,
    "Dezember": 0.19,
    "Januar": 0.185,
    "Februar": 0.165,
    "Maerz": 0.145,
    "April": 0.09,
}
TAGE_HEIZPERIODE = 212  # ca. 15.10. - 15.04.


@dataclass
class Auslegung:
    wohnflaeche_m2: float
    heizwaermebedarf: float = DEFAULT_HEIZWAERMEBEDARF
    trinkwarmwasser: float = DEFAULT_TRINKWARM
    anfangstemperatur: float = 20.0   # °C, Beladung des Speichers zu Heizbeginn
    lichte_hoehe_m: float = 3.0        # m, lichte Höhe des Speichers
    nutzungsgrad: float = 0.9         # Anteil des theoretisch nutzbaren Speichers
    netz_vorlauf_c: float = 10.0      # °C, Vorlauf des kalten Wärmenetzes
    netz_ruecklauf_c: float = 5.0     # °C, Rücklauf des kalten Wärmenetzes
    heizung_vorlauf_c: float = 35.0   # °C, Vorlauf der Gebäudeheizung (Booster-Ziel)
    guetegrad: float = 0.5            # Gütegrad der Booster-Wärmepumpen
    cop_mittel: float | None = None   # optional: fester COP statt Temperatur-Abschätzung
    monate: dict = field(default_factory=lambda: dict(HEIZPERIODE_MONATE))

    @property
    def jahres_raumwaerme_kwh(self) -> float:
        return self.wohnflaeche_m2 * self.heizwaermebedarf

    @property
    def jahres_trinkwarm_kwh(self) -> float:
        return self.wohnflaeche_m2 * self.trinkwarmwasser

    @property
    def winteranteil_raumwaerme(self) -> float:
        return sum(self.monate.values())

    @property
    def winter_waermebedarf_kwh(self) -> float:
        raum = self.jahres_raumwaerme_kwh * self.winteranteil_raumwaerme
        warm = self.jahres_trinkwarm_kwh * TAGE_HEIZPERIODE / 365.0
        return raum + warm

    @property
    def quelle_c(self) -> float:
        # Quellentemperatur der Booster = Vorlauf des kalten Netzes;
        # das Netz liegt konstant bei 10-15 °C, daher kein Abtauen nötig
        return self.netz_vorlauf_c

    @property
    def hysterese_c(self) -> float:
        # Vorlauf muss im Heizbetrieb immer höher sein als Rücklauf
        if self.netz_vorlauf_c <= self.netz_ruecklauf_c:
            raise ValueError(
                "Netz-Vorlauf muss höher als Netz-Rücklauf sein (VL > RL)"
            )
        return self.netz_vorlauf_c - self.netz_ruecklauf_c

    @property
    def energie_pro_m3_netz_kwh(self) -> float:
        # Energie, die die Booster pro m³ Netzumlauf aus der Hysterese ziehen
        return RHO_WASSER * C_WASSER * self.hysterese_c / 1000.0

    @property
    def leistung_quelle_kw(self) -> float:
        # mittlere Quellenleistung über die Heizperiode
        return self.quellenenergie_kwh / (TAGE_HEIZPERIODE * 24.0)

    @property
    def volumenstrom_netz_m3h(self) -> float:
        # nötiger Volumenstrom des kalten Netzes aus der Hysterese
        return self.leistung_quelle_kw / self.energie_pro_m3_netz_kwh

    @property
    def cop_booster(self) -> float:
        if self.cop_mittel is not None:
            return self.cop_mittel
        t_h = self.heizung_vorlauf_c + 273.15
        t_q = self.quelle_c + 273.15
        if t_h <= t_q:
            raise ValueError(
                "Heizungs-Vorlauf muss über der Netz-Vorlauftemperatur liegen"
            )
        return self.guetegrad * t_h / (t_h - t_q)

    @property
    def nutzbar_pro_m3_kwh(self) -> float:
        sensibel = RHO_WASSER * C_WASSER * self.anfangstemperatur / 1000.0
        return (LATENT_WAERME + sensibel) * self.nutzungsgrad

    @property
    def quellenenergie_kwh(self) -> float:
        # Der Speicher ist die Wärmequelle der Booster-Wärmepumpen:
        # gespeicherte Energie = abgegebene Heizwärme / COP
        return self.winter_waermebedarf_kwh / self.cop_booster

    @property
    def volumen_m3(self) -> float:
        return self.quellenenergie_kwh / self.nutzbar_pro_m3_kwh

    @property
    def grundflaeche_m2(self) -> float:
        return self.volumen_m3 / self.lichte_hoehe_m

    @property
    def tank_durchmesser_m(self) -> float:
        return math.sqrt(4.0 * self.grundflaeche_m2 / math.pi)


def de(num: float, nachkomma: int = 0) -> str:
    """Zahl im deutschen Format (Punkt als Tausendertrennzeichen)."""
    return f"{num:,.{nachkomma}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def bericht(a: Auslegung) -> str:
    zeilen = [
        "=== Eisspeicher-Auslegung (ohne Regeneration) ===",
        f"Beheizte Wohnfläche:            {de(a.wohnflaeche_m2)} m²",
        f"Heizwärmebedarf:                {a.heizwaermebedarf:.1f} kWh/(m²·a)",
        f"Jahres-Raumwärmebedarf:         {de(a.jahres_raumwaerme_kwh/1e6, 3)} GWh",
        f"Jahres-Trinkwarmwasser:         {de(a.jahres_trinkwarm_kwh/1e3)} MWh",
        f"Wärmebedarf Heizperiode:        {de(a.winter_waermebedarf_kwh/1e6, 3)} GWh",
        f"Kaltes Netz:                    Vorlauf {a.netz_vorlauf_c:.1f} °C (Quelle), "
        f"Rücklauf {a.netz_ruecklauf_c:.1f} °C",
        f"Quellentemperatur Booster:      {a.quelle_c:.1f} °C (Netz-Vorlauf)",
        f"Hysterese kaltes Netz (VL-RL):  {a.hysterese_c:.1f} K "
        f"= {a.energie_pro_m3_netz_kwh:.2f} kWh pro m³ Netzumlauf",
        f"Mittlere Quellenleistung:       {a.leistung_quelle_kw:.1f} kW",
        f"Volumenstrom kaltes Netz:       {de(a.volumenstrom_netz_m3h, 1)} m³/h",
        f"Heizungs-Vorlauf (Booster):     {a.heizung_vorlauf_c:.1f} °C, "
        f"Gütegrad {a.guetegrad:.2f}",
        f"COP Booster (abgeschätzt):      {a.cop_booster:.2f}",
        f"Benötigte Quellenenergie:       {de(a.quellenenergie_kwh/1e3)} MWh",
        f"Anfangsbeladung Speicher:       {a.anfangstemperatur:.1f} °C",
        f"Nutzbar pro m³ Speicher:        {a.nutzbar_pro_m3_kwh:.1f} kWh/m³ "
        f"(latent {LATENT_WAERME:.1f} + sensibel, Nutzungsgrad {a.nutzungsgrad:.0%})",
        f"Erforderliches Speichervolumen: {de(a.volumen_m3)} m³",
        f"  = {a.volumen_m3/a.wohnflaeche_m2:.3f} m³ pro m² Wohnfläche",
        f"  = Eismasse ca. {de(a.volumen_m3*RHO_WASSER/1e6, 2)} Mio. kg",
        f"Lichte Höhe:                    {a.lichte_hoehe_m:.2f} m",
        f"  => Grundfläche:               {de(a.grundflaeche_m2, 1)} m²",
        f"  => Zylinderdurchmesser:        ca. {de(a.tank_durchmesser_m, 1)} m",
    ]
    return "\n".join(zeilen)


def main() -> None:
    p = argparse.ArgumentParser(
        description="Auslegung eines Eisspeichers für eine Heizperiode ohne Regeneration"
    )
    p.add_argument("--wohnflaeche", type=float, default=40000.0,
                   help="beheizte Wohnfläche in m² (Default: 40000)")
    p.add_argument("--standard", choices=list(GEBAEUDESTANDARDS), default=None,
                   help="Gebäudestandard; setzt den Heizwärmebedarf, falls nicht explizit angegeben")
    p.add_argument("--heizwaermebedarf", type=float, default=None,
                   help="kWh/(m²·a), KfW EH40-EE typisch 25-40 (Default: Wert des Standards bzw. 35)")
    p.add_argument("--trinkwarmwasser", type=float, default=DEFAULT_TRINKWARM,
                   help="kWh/(m²·a) (Default: 12.5)")
    p.add_argument("--anfangstemperatur", type=float, default=20.0,
                   help="Beladung des Speichers zu Beginn der Heizperiode in °C (Default: 20)")
    p.add_argument("--lichte-hoehe", type=float, default=3.0,
                   help="lichte Höhe des Speichers in m (Default: 3)")
    p.add_argument("--nutzungsgrad", type=float, default=0.9,
                   help="nutzbarer Anteil des Speichers (Default: 0.9)")
    p.add_argument("--netz-vorlauf", type=float, default=10.0,
                   help="Vorlauftemperatur kaltes Wärmenetz in °C (Default: 10)")
    p.add_argument("--netz-ruecklauf", type=float, default=5.0,
                   help="Rücklauftemperatur kaltes Wärmenetz in °C (Default: 5)")
    p.add_argument("--heizung-vorlauf", type=float, default=35.0,
                   help="Vorlauftemperatur der Gebäudeheizung in °C (Default: 35)")
    p.add_argument("--guetegrad", type=float, default=0.5,
                   help="Gütegrad der Booster-Wärmepumpen (Default: 0.5)")
    p.add_argument("--cop", type=float, default=None,
                   help="optional: fester COP statt Abschätzung aus Temperaturen")
    args = p.parse_args()

    if args.heizwaermebedarf is not None:
        heizwaermebedarf = args.heizwaermebedarf
    elif args.standard is not None:
        heizwaermebedarf = GEBAEUDESTANDARDS[args.standard]
    else:
        heizwaermebedarf = DEFAULT_HEIZWAERMEBEDARF

    a = Auslegung(
        wohnflaeche_m2=args.wohnflaeche,
        heizwaermebedarf=heizwaermebedarf,
        trinkwarmwasser=args.trinkwarmwasser,
        anfangstemperatur=args.anfangstemperatur,
        lichte_hoehe_m=args.lichte_hoehe,
        nutzungsgrad=args.nutzungsgrad,
        netz_vorlauf_c=args.netz_vorlauf,
        netz_ruecklauf_c=args.netz_ruecklauf,
        heizung_vorlauf_c=args.heizung_vorlauf,
        guetegrad=args.guetegrad,
        cop_mittel=args.cop,
    )
    print(bericht(a))


if __name__ == "__main__":
    main()
