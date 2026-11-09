# Eisspeicher

Python-Tool zur Auslegung eines Eisspeichers als Wärmequelle über ein kaltes Wärmenetz mit Booster-Wärmepumpen (eine Heizperiode ohne Regeneration).

## Web-UI

```
python3 ui.py        # http://localhost:8000
```

Alle Eingaben sind Pflichtfelder: Wohnfläche, Heizwärmebedarf, Trinkwarmwasser, Anfangsbeladung des Speichers, lichte Höhe, Nutzungsgrad, Vorlauf/Rücklauf des kalten Netzes, Heizungs-Vorlauf, Gütegrad der Booster.

## CLI

```
python3 eisspeicher.py --wohnflaeche 40000 --anfangstemperatur 20 --lichte-hoehe 3 --netz-vorlauf 6 --netz-ruecklauf 12 --heizung-vorlauf 35
```

## Tests

```
python3 -m pytest test_eisspeicher.py   # oder jeder Test einzeln ohne pytest
```
