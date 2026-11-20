"""Ein Sensor mit der Übersicht der angelegten Personen (für das Dashboard).

Der Zustand ist die Anzahl der Personen; die Namen samt Stand und Zeitpunkten hängen als Angaben daran
(siehe report.py). Zugangsdaten stehen nirgends darin — store.overview() liefert sie gar nicht erst.
"""
from __future__ import annotations

from datetime import timedelta

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from .const import DOMAIN
from .report import overview_attributes

SCAN_INTERVAL = timedelta(minutes=5)


async def async_setup_platform(hass: HomeAssistant, config: ConfigType, add_entities, discovery_info: DiscoveryInfoType | None = None) -> None:
    daten = hass.data.get(DOMAIN)
    if not daten:
        return
    add_entities([AikidoPersonsSensor(daten["store"], daten["max_persons"])], True)


class AikidoPersonsSensor(SensorEntity):
    _attr_has_entity_name = False
    _attr_name = "Aikido Tracker Personen"
    _attr_unique_id = "aikido_tracker_personen"
    _attr_icon = "mdi:account-key"
    _attr_native_unit_of_measurement = "Personen"

    def __init__(self, store, max_persons: int) -> None:
        self._store = store
        self._max_persons = max_persons
        self._attrs: dict = {}
        self._anzahl = 0

    @property
    def native_value(self) -> int:
        return self._anzahl

    @property
    def extra_state_attributes(self) -> dict:
        return self._attrs

    async def async_update(self) -> None:
        angaben = overview_attributes(self._store.overview(), self._max_persons)
        self._anzahl = angaben["anzahl"]
        self._attrs = angaben
