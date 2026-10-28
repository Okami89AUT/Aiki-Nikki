"""Aikido Tracker – zentraler Speicher für den „Aikido Kyu Tracker“ (Anbindung an Home Assistant).

Die eigentliche Arbeit steckt in store.py (Speicherung) und api.py (Schnittstelle); beide kennen Home Assistant nicht.
Diese Datei richtet nur ein: Einstellungen lesen, Speicher laden, die Aufrufe unter /api/aikido_tracker/… anmelden.
"""
from __future__ import annotations

import logging
import os
from datetime import timedelta

import voluptuous as vol

from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.typing import ConfigType

from .api import PREFIX, ROUTES, Api
from .const import (
    CONF_DATA_DIR,
    CONF_HISTORY_DAYS,
    CONF_INVITE_CODE,
    CONF_MAX_PERSONS,
    CONF_PAGE_FILE,
    DEFAULT_DATA_DIRNAME,
    DEFAULT_HISTORY_DAYS,
    DEFAULT_MAX_PERSONS,
    DOMAIN,
    MAX_CODE_LEN,
    MIN_CODE_LEN,
)
from .page import PAGE_URL, make_page_handler, resolve_page_path
from .store import PersonStore, StoreError, is_inside

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Any(
            None,
            vol.Schema(
                {
                    vol.Optional(CONF_INVITE_CODE): vol.All(cv.string, vol.Length(min=MIN_CODE_LEN, max=MAX_CODE_LEN)),
                    vol.Optional(CONF_MAX_PERSONS, default=DEFAULT_MAX_PERSONS): vol.All(vol.Coerce(int), vol.Range(min=1, max=200)),
                    vol.Optional(CONF_HISTORY_DAYS, default=DEFAULT_HISTORY_DAYS): vol.All(vol.Coerce(int), vol.Range(min=0, max=365)),
                    vol.Optional(CONF_DATA_DIR): cv.string,
                    vol.Optional(CONF_PAGE_FILE): cv.string,
                }
            ),
        )
    },
    extra=vol.ALLOW_EXTRA,
)

_PRUNE_EVERY = timedelta(hours=6)


def _make_view(method: str, path: str, handler) -> type[HomeAssistantView]:
    """Eine Ansicht je Aufruf; die Anmeldung läuft über Name + Zugangscode, nicht über Home Assistant."""

    async def respond(self, request):
        return await handler(request)

    return type(
        f"AikidoTracker_{path.replace('-', '_')}_View",
        (HomeAssistantView,),
        {
            "url": f"{PREFIX}/{path}",
            "name": f"api:{DOMAIN}:{path}",
            "requires_auth": False,
            "cors_allowed": False,
            method.lower(): respond,
        },
    )


def _make_page_view(path_getter) -> type[HomeAssistantView]:
    """Die App-Seite unter /aikido-tracker (mit Zwischenspeicher-Regeln, die Updates sofort sichtbar machen)."""
    handler = make_page_handler(path_getter)

    async def get(self, request):
        return await handler(request)

    return type(
        "AikidoTrackerPageView",
        (HomeAssistantView,),
        {
            "url": PAGE_URL,
            "extra_urls": [PAGE_URL + "/"],
            "name": f"{DOMAIN}:page",
            "requires_auth": False,
            "cors_allowed": False,
            "get": get,
        },
    )


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    conf = config.get(DOMAIN) or {}
    package_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = hass.config.path(conf.get(CONF_DATA_DIR) or DEFAULT_DATA_DIRNAME)
    if is_inside(data_dir, package_dir):
        # HACS ersetzt bei jeder Aktualisierung den ganzen Ordner des Bausteins – Daten darin wären danach weg.
        _LOGGER.error(
            "Aikido Tracker: Der Datenordner %s liegt im Ordner des Bausteins (%s). Bei einer Aktualisierung "
            "über HACS würden die Daten gelöscht. Bitte data_dir ändern (Standard: aikido_tracker neben custom_components).",
            data_dir,
            package_dir,
        )
        return False
    store = PersonStore(
        data_dir,
        history_days=conf.get(CONF_HISTORY_DAYS, DEFAULT_HISTORY_DAYS),
        max_persons=conf.get(CONF_MAX_PERSONS, DEFAULT_MAX_PERSONS),
    )
    try:
        await store.async_load()
    except StoreError as err:
        _LOGGER.error("Aikido Tracker: Datenordner %s nicht nutzbar: %s", data_dir, err)
        return False

    invite = conf.get(CONF_INVITE_CODE)
    api = Api(store, invite_code=invite)
    for method, path, handler_name in ROUTES:
        hass.http.register_view(_make_view(method, path, getattr(api, handler_name)))
    page_file = resolve_page_path(hass.config.config_dir, conf.get(CONF_PAGE_FILE), package_dir)
    hass.http.register_view(_make_page_view(lambda: page_file))

    async def _prune(_now) -> None:
        try:
            await store.prune()
        except StoreError as err:
            _LOGGER.warning("Aikido Tracker: Aufräumen der Tagessicherungen fehlgeschlagen: %s", err)

    async_track_time_interval(hass, _prune, _PRUNE_EVERY)

    if invite is None:
        _LOGGER.warning(
            "Aikido Tracker: kein invite_code eingestellt – neue Personen können nicht angelegt werden (vorhandene bleiben nutzbar)"
        )
    _LOGGER.info("Aikido Tracker bereit: %d Person(en), Daten in %s, App-Seite aus %s", store.count(), data_dir, page_file)
    return True
