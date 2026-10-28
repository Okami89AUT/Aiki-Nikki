"""Zähler in gleitenden Zeitfenstern (nur im Arbeitsspeicher, einfädig im Event-Loop benutzt)."""
from __future__ import annotations

import math
from collections import deque


class SlidingLog:
    """Merkt sich die Zeitpunkte von Ereignissen je Schlüssel (Adresse, Person …).

    * retry_after(key, now) -> 0, wenn noch Platz ist; sonst die Sekunden bis wieder ein Ereignis zulässig ist.
    * add(key, now)         -> verbucht ein Ereignis und gibt eine Marke zurück,
    * discard(key, marke)   -> nimmt es wieder heraus (z. B. wenn die Anmeldung doch gelungen ist).
    Prüfen und Verbuchen laufen ohne `await` dazwischen – dadurch können auch gleichzeitige Anfragen
    das Limit nicht „überholen“.
    """

    def __init__(self, limit: int, window: float, max_keys: int) -> None:
        self.limit = limit
        self.window = window
        self.max_keys = max_keys
        self._events: dict[str, deque] = {}

    def _trim(self, key: str, now: float):
        queue = self._events.get(key)
        if queue is None:
            return None
        while queue and now - queue[0] >= self.window:
            queue.popleft()
        if not queue:
            del self._events[key]
            return None
        return queue

    def count(self, key: str, now: float) -> int:
        queue = self._trim(key, now)
        return len(queue) if queue else 0

    def retry_after(self, key: str, now: float) -> int:
        queue = self._trim(key, now)
        if queue is None or len(queue) < self.limit:
            return 0
        # frei wird es, sobald so viele alte Ereignisse abgelaufen sind, dass wieder Platz ist
        blocking = queue[len(queue) - self.limit]
        return max(1, math.ceil(blocking + self.window - now))

    def add(self, key: str, now: float) -> float:
        if key not in self._events and len(self._events) >= self.max_keys:
            self._make_room(now)
        self._events.setdefault(key, deque()).append(now)
        return now

    def discard(self, key: str, stamp: float) -> None:
        queue = self._events.get(key)
        if queue is None:
            return
        try:
            queue.remove(stamp)
        except ValueError:
            pass
        if not queue:
            del self._events[key]

    def _make_room(self, now: float) -> None:
        for key in list(self._events):
            self._trim(key, now)
        overflow = len(self._events) - self.max_keys + 1
        if overflow > 0:
            for key in list(self._events)[:overflow]:  # die ältesten Schlüssel zuerst
                del self._events[key]
