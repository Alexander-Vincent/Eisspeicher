#!/usr/bin/env python3
"""Auslegung eines Eisspeichers (Wärmequellen-Speicher für eine Wärmepumpe).

Sizing only: dimensioniert das Wasservolumen, das nötig ist, um eine
Heizperiode ohne Zwischenregeneration allein aus dem Eisspeicher zu
bedienen. Eine zeitliche Simulation (Regeneration, Solarabsorber,
Lastprofile) ist als nächster Schritt vorgesehen.
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
DEFAULT_TRINKWARM = 12.5          # kWh/(m^2*a) nach DIN V 4701-10

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
    cop_mittel: float = 3.2          # mittlerer COP bei Quellentemperatur um 0 °C
    starttemperatur: float = 10.0    # °C, Wassertemperatur zu Saisonbeginn
    nutzungsgrad: float = 0.9        # Anteil des theoretisch nutzbaren Speichers
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
    def nutzbar_pro_m3_kwh(self) -> float:
        sensibel = RHO_WASSER * C_WASSER * self.starttemperatur / 1000.0
        return (LATENT_WAERME + sensibel) * self.nutzungsgrad

    @property
    def quellenenergie_kwh(self) -> float:
        # Der Speicher ist die Wärmequelle der Wärmepumpe:
        # gespeicherte Energie = abgegebene Heizwärme / COP
        return self.winter_waermebedarf_kwh / self.cop_mittel

    @property
    def volumen_m3(self) -> float:
        return self.quellenenergie_kwh / self.nutzbar_pro_m3_kwh

    def tank_durchmesser(self, wassHoehe_m: float = 3.0) -> float:
        return math.sqrt(4.0 * self.volumen_m3 / (math.pi * wassHoehe_m))


def de(num: float, nachkomma: int = 0) -> str:
    """Zahl im deutschen Format (Punkt als Tausendertrennzeichen)."""
    return f"{num:,.{nachkomma}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def bericht(a: Auslegung, wasserhoehe_m: float) -> str:
    zeilen = [
        "=== Eisspeicher-Auslegung (ohne Regeneration) ===",
        f"Beheizte Wohnfläche:            {de(a.wohnflaeche_m2)} m²",
        f"Heizwärmebedarf (EH40-EE):      {a.heizwaermebedarf:.1f} kWh/(m²·a)",
        f"Jahres-Raumwärmebedarf:         {de(a.jahres_raumwaerme_kwh/1e6, 3)} GWh",
        f"Jahres-Trinkwarmwasser:         {de(a.jahres_trinkwarm_kwh/1e3)} MWh",
        f"Winteranteil Raumwärme:         {a.winteranteil_raumwaerme*100:.1f} %",
        f"Wärmebedarf Heizperiode:        {de(a.winter_waermebedarf_kwh/1e6, 3)} GWh",
        f"Mittlerer COP (Quelle ~0 °C):   {a.cop_mittel:.2f}",
        f"Benötigte Quellenenergie:       {de(a.quellenenergie_kwh/1e3)} MWh",
        f"Nutzbar pro m³ Speicher:        {a.nutzbar_pro_m3_kwh:.1f} kWh/m³ "
        f"(latent {LATENT_WAERME:.1f} + sensibel, Nutzungsgrad {a.nutzungsgrad:.0%})",
        f"Erforderliches Speichervolumen: {de(a.volumen_m3)} m³",
        f"  = {a.volumen_m3/a.wohnflaeche_m2:.3f} m³ pro m² Wohnfläche",
        f"  = Eismasse ca. {de(a.volumen_m3*RHO_WASSER/1e6, 2)} Mio. kg",
        f"Zylindrischer Tank bei {wasserhoehe_m:.1f} m Wasserhöhe: "
        f"Durchmesser ca. {de(a.tank_durchmesser(wasserhoehe_m), 1)} m",
    ]
    return "\n".join(zeilen)


def main() -> None:
    p = argparse.ArgumentParser(
        description="Auslegung eines Eisspeichers für eine Heizperiode ohne Regeneration"
    )
    p.add_argument("--wohnflaeche", type=float, default=40000.0,
                   help="beheizte Wohnfläche in m² (Default: 40000)")
    p.add_argument("--heizwaermebedarf", type=float, default=DEFAULT_HEIZWAERMEBEDARF,
                   help="kWh/(m²·a), KfW EH40-EE typisch 25-40 (Default: 35)")
    p.add_argument("--cop", type=float, default=3.2,
                   help="mittlerer COP der Wärmepumpe bei Eis als Quelle (Default: 3.2)")
    p.add_argument("--starttemperatur", type=float, default=10.0,
                   help="Wassertemperatur zu Beginn der Heizperiode in °C (Default: 10)")
    p.add_argument("--nutzungsgrad", type=float, default=0.9,
                   help="nutzbarer Anteil des Speichers (Default: 0.9)")
    p.add_argument("--wasserhoehe", type=float, default=3.0,
                   help="angenommene Wasserhöhe eines zylindrischen Tanks in m (Default: 3)")
    args = p.parse_args()

    a = Auslegung(
        wohnflaeche_m2=args.wohnflaeche,
        heizwaermebedarf=args.heizwaermebedarf,
        cop_mittel=args.cop,
        starttemperatur=args.starttemperatur,
        nutzungsgrad=args.nutzungsgrad,
    )
    print(bericht(a, args.wasserhoehe))


if __name__ == "__main__":
    main()
