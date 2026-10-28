"""Liefert die App-Seite (eine HTML-Datei) mit Zwischenspeicher-Regeln, die Aktualisierungen sofort sichtbar machen.

Hintergrund: Dateien aus dem Ordner www liefert Home Assistant unter /local/… mit "max-age" von 31 Tagen aus –
ein Browser fragt dann wochenlang nicht nach einer neueren Fassung. Diese Ansicht sagt stattdessen "no-cache":
der Browser fragt jedes Mal kurz nach (ETag) und lädt nur bei Änderung neu.

Die App liegt im Baustein selbst (app/aikido-kyu-tracker.html): HACS installiert und aktualisiert Server und App
gemeinsam, beide passen immer zusammen. Mit `page_file` in der Konfiguration lässt sich eine andere Datei einstellen.
"""
from __future__ import annotations

import asyncio
import os
from collections.abc import Callable

from aiohttp import web

PAGE_URL = "/aikido-tracker"
BUNDLED_DIR = "app"                          # Ordner im Baustein
BUNDLED_FILE = "aikido-kyu-tracker.html"     # die mitgelieferte App
_MISSING_TEXT = (
    "Die App-Seite fehlt auf dem Server. Installiere den Baustein „Aikido Tracker“ neu "
    "(in HACS: Neu herunterladen) oder prüfe die Einstellung page_file."
)


def resolve_page_path(config_dir: str, configured: str | None, package_dir: str) -> str:
    """Welche Datei unter /aikido-tracker ausgeliefert wird.

    Standard: die im Baustein mitgelieferte App. Mit `page_file` (relativ zum Konfigurationsordner oder absolut)
    wird stattdessen diese Datei ausgeliefert; ein leerer Wert zählt als nicht eingestellt.
    """
    if configured:
        return os.path.join(config_dir, configured)
    return os.path.join(package_dir, BUNDLED_DIR, BUNDLED_FILE)


def make_page_handler(path_getter: Callable[[], str]):
    async def handler(request: web.Request) -> web.StreamResponse:
        path = path_getter()
        if not await asyncio.get_running_loop().run_in_executor(None, os.path.isfile, path):
            return web.Response(
                status=404,
                text=_MISSING_TEXT,
                content_type="text/plain",
                charset="utf-8",
                headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
            )
        return web.FileResponse(
            path,
            headers={
                "Content-Type": "text/html; charset=utf-8",
                "Cache-Control": "no-cache",
                "X-Content-Type-Options": "nosniff",
            },
        )

    return handler


def add_page_route(app: web.Application, path_getter: Callable[[], str]) -> None:
    handler = make_page_handler(path_getter)
    app.router.add_get(PAGE_URL, handler)
    app.router.add_get(PAGE_URL + "/", handler)
