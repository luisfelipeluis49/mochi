"""Mochi's face: tells the page on Mochi's own screen (hardware/pi-setup/face.html) what Mochi is doing.

One server-sent-events endpoint on localhost. The page keeps the latest state and draws it; it
reconnects by itself, and with no page open this costs nothing.

    mode   sleeping | waking | awake | hearing | thinking | speaking | bye
    mood   neutral | happy | excited | love | laughing | surprised | curious | proud | oops | cool | sleepy
    level  0-100, loudness of Mochi's own voice right now
    word   a word shown big under the face
    note   a smaller line under the word: its language and what it means ("English · garfo")
    pop    {"what": "volume" | "temp", "value": n, "n": counter}: a badge shown for a few seconds
    who    the name of the person Mochi recognises talking ("" = nobody)
    temp   Mochi's own temperature in whole degrees Celsius (None = not known): always shown while it sleeps
    hot    True while that is too warm ([alerts].hot_at): the temperature is then shown whatever Mochi does
    online False while Mochi has no connection to the internet: the face says so
    round  a Describe & Guess round in front of the face, or None:
           {"tone": "ask" | "secret" | "result", "big": the large line, "small": the line under it}

The other way, the page reports touches: GET /tap?kind=tap | long (a long press), passed to on_tap.
"""
from __future__ import annotations

import asyncio
import json

MOODS = ("neutral", "happy", "excited", "love", "laughing", "surprised", "curious", "proud", "oops", "cool", "sleepy")


class Face:
    def __init__(self, cfg: dict | None = None):
        cfg = cfg or {}
        self.enabled = cfg.get("enabled", True)
        self.host, self.port = cfg.get("host", "127.0.0.1"), int(cfg.get("port", 8765))
        self.state: dict = {"mode": "sleeping", "mood": "neutral", "level": 0, "word": "", "note": "", "pop": None,
                            "who": "", "round": None, "temp": None, "hot": False,
                            "online": True}
        self.on_tap = None  # on_tap(kind): the screen was touched ("tap") or held ("long")
        self._changed: set[asyncio.Event] = set()  # one per connected page
        self._server: asyncio.AbstractServer | None = None
        self._timers: dict[str, asyncio.TimerHandle] = {}
        self._pops = 0

    async def start(self) -> None:
        if not self.enabled:
            return
        try:
            self._server = await asyncio.start_server(self._serve, self.host, self.port)
        except OSError as e:  # port taken: Mochi works without a face
            print(f"[mochi] face not available on {self.host}:{self.port}: {e}", flush=True)

    async def stop(self) -> None:
        if self._server:
            self._server.close()

    def set(self, **changes) -> None:
        """Change what the face shows; pages are told only when something really changed."""
        changes = {k: v for k, v in changes.items() if self.state.get(k) != v}
        if changes:
            self.state.update(changes)
            for e in self._changed:
                e.set()

    def show_for(self, seconds: float, **changes) -> None:
        """Like set(), and puts each key back to its resting value after a while."""
        rest = {"mood": "neutral", "word": "", "note": "", "pop": None, "who": "", "round": None}
        self.set(**changes)
        for key in changes:
            if key in self._timers:
                self._timers[key].cancel()
            self._timers[key] = asyncio.get_running_loop().call_later(seconds, lambda k=key: self.set(**{k: rest[k]}))

    def keep(self, **changes) -> None:
        """Like set(), and it stays: a show_for() still counting down for these keys no longer applies."""
        for key in changes:
            if key in self._timers:
                self._timers.pop(key).cancel()
        self.set(**changes)

    def pop(self, what: str, value: float) -> None:
        self._pops += 1
        self.show_for(5, pop={"what": what, "value": value, "n": self._pops})

    async def _serve(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        changed = asyncio.Event()
        try:
            request = await asyncio.wait_for(reader.readline(), timeout=5)
            while (await asyncio.wait_for(reader.readline(), timeout=5)).strip():
                pass  # headers
            if request.startswith(b"GET /tap"):  # the page is a local file, so any origin may call (reachable locally only)
                if self.on_tap:
                    self.on_tap("long" if b"kind=long" in request else "tap")
                writer.write(b"HTTP/1.1 204 No Content\r\nAccess-Control-Allow-Origin: *\r\nConnection: close\r\n\r\n")
                await writer.drain()
                return
            if b" /events" not in request:
                writer.write(b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
                await writer.drain()
                return
            # the page is opened from a file, so any origin may listen (it is only reachable locally)
            writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\nCache-Control: no-cache\r\n"
                         b"Access-Control-Allow-Origin: *\r\nConnection: keep-alive\r\n\r\n")
            self._changed.add(changed)
            while True:
                changed.clear()
                writer.write(f"data: {json.dumps(self.state)}\n\n".encode())
                await writer.drain()
                try:
                    await asyncio.wait_for(changed.wait(), timeout=15)
                except asyncio.TimeoutError:
                    pass  # resend as a keep-alive; a closed page then shows up as a write error
        except (ConnectionError, asyncio.TimeoutError, asyncio.IncompleteReadError):
            pass
        finally:
            self._changed.discard(changed)
            writer.close()
