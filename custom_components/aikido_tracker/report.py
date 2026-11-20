"""Aufbereitung der Personen-Übersicht für die Anzeige in Home Assistant.

Dieses Modul kennt weder Home Assistant noch Dateien: Es formt die Liste aus store.overview() in die Angaben um,
die am Sensor hängen. Zugangsdaten tauchen hier nicht auf — store.overview() liefert sie gar nicht erst.
"""


def overview_attributes(persons, max_persons: int) -> dict:
    """Angaben für den Sensor: die Personen in Klartext plus ein paar Zahlen."""
    personen = [
        {
            "name": p["name"],
            "kennung": p["id"],
            "stand": p["rev"],
            "zuletzt": p["updated_at"],
            "angelegt": p["created"],
            "loeschung": p["delete_at"] or None,
            "lesbar": not p["unreadable"],
        }
        for p in persons
    ]
    return {
        "personen": personen,
        "anzahl": len(personen),
        "maximal": int(max_persons),
        "unlesbar": sum(1 for p in personen if not p["lesbar"]),
        "loeschungen": sum(1 for p in personen if p["loeschung"]),
    }
