"""Silent commands: what Mochi writes in square brackets moves its body and is never spoken.

`[mood happy]` and `[show queue]` go to its face, `[volume 80]` to its speaker, `[temp]` shows its
temperature, `[enroll Ana pt]` / `[forget Ana]` learn and forget a voice, `[bye]` ends the session
once Mochi's goodbye has been heard. The device reads them from its state (`commands`) and does each
one once. A hint adds a command of its own that Mochi does not write: `hint`, whose value is a JSON
card (`word`, `language`, `meaning`, `example`, `why`). So do the live transcript (`caption`:
`who`, `text`) and an explained idiom or term (`explain`: `word`, `meaning`, `plain`, `kind`), D-51
to D-53.
"""

import re
from datetime import datetime, timedelta

from pydantic import BaseModel, Field

_COMMAND = re.compile(
    r"\[\s*(volume|mood|show|temp|enroll|forget|bye)\b\s*:?\s*([^\]]*?)\s*\]", re.IGNORECASE
)
_BRACKETS = re.compile(r"\[[^\]]*\]")
QUEUE_LIMIT = 20
COMMAND_LIFETIME = timedelta(seconds=30)  # a restarted device must not replay old orders

Written = tuple[str, str]  # (kind, value) as found in a reply


class DeviceCommand(BaseModel):
    """One thing for the device to do. `command_id` lets it do each one only once."""

    command_id: str
    kind: str
    value: str
    at: datetime | None = Field(default=None, exclude=True)  # when queued; never on the wire


def split_commands(text: str) -> tuple[str, list[Written]]:
    """The words to say, and the commands that were written among them.

    Example: `"[mood cool][volume 80] Louder it is!"` ->
    `("Louder it is!", [("mood", "cool"), ("volume", "80")])`. Any other bracket is dropped too.
    """
    written = [(m.group(1).lower(), m.group(2)) for m in _COMMAND.finditer(text)]
    return " ".join(_BRACKETS.sub(" ", text).split()), written
