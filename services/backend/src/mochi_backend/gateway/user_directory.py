"""The people the backend knows: `ana` and `ben` (the Pi's), and users the web app creates (D-42).

A web user's id is a slug of the name plus 6 random hex characters, so it never equals `ana`, `ben`
or `guest`. `guest` is reserved: it is the second participant of every web session, with the user's
languages the other way round, so the whose-word rule (AGENTS 7.3) still finds one learner.
"""

import re
import secrets
import unicodedata
from typing import Protocol

from mochi_backend.gateway.errors import ConflictError
from mochi_backend.gateway.roster import DEMO_USERS, GUEST_ID
from mochi_backend.storage.port import Storage
from mochi_contracts import Language, Participant, User

SLUG_LIMIT = 20
SUFFIX_DRAWS = 16  # a collision of 6 hex characters is rare; 16 in a row means a broken source
WEB_USER_ID = re.compile(r"^[a-z0-9-]+-[0-9a-f]{6}$")


class SuffixSource(Protocol):
    """Where the 6 random hex characters of a new user id come from."""

    def suffix(self) -> str:
        """Six lowercase hex characters, e.g. `"3f9c1a"`."""
        ...


class RandomSuffix:
    """Implements `SuffixSource` with the OS's random source. Example: `RandomSuffix().suffix()`."""

    def suffix(self) -> str:
        """Six random lowercase hex characters."""
        return secrets.token_hex(3)


def slug_of(display_name: str) -> str:
    """The id-safe part of a name: ASCII, lowercase, runs of anything else as one `-`, 20 at most.

    Example: `slug_of("Luís Felipe")` is `"luis-felipe"`; `slug_of("李")` is `"user"`.
    """
    folded = unicodedata.normalize("NFKD", display_name)
    ascii_only = "".join(c for c in folded if not unicodedata.combining(c)).encode(
        "ascii", "ignore"
    )
    dashed = re.sub(r"[^a-z0-9]+", "-", ascii_only.decode().lower()).strip("-")
    return dashed[:SLUG_LIMIT].strip("-") or "user"


def is_web_user(user_id: str) -> bool:
    """True for an id the web app's onboarding made. Example: `is_web_user("ana")` is False."""
    return WEB_USER_ID.fullmatch(user_id) is not None


def session_participants(user: User) -> list[Participant]:
    """A web session's two people: the user, and `guest` with the user's languages reversed.

    Example: for a user at home in pt-BR learning en, the guest is at home in en learning pt-BR.
    """
    guest = Participant(
        user_id=GUEST_ID,
        comfortable_languages=[user.target_language],
        target_language=user.comfortable_languages[0],
    )
    own = Participant(
        user_id=user.user_id,
        comfortable_languages=list(user.comfortable_languages),
        target_language=user.target_language,
    )
    return [own, guest]


def voice_owners(stored: list[User]) -> list[User]:
    """The people a voice name may belong to: the Pi's people only, `ana` and `ben` first.

    A web user may well be called "Ana"; the voice "Ana" must still be `ana`'s.
    Example: `[u.user_id for u in voice_owners([])]` is `["ana", "ben"]`.
    """
    demo_ids = {user.user_id for user in DEMO_USERS}
    others = [
        user
        for user in stored
        if user.user_id not in demo_ids
        and user.user_id != GUEST_ID
        and not is_web_user(user.user_id)
    ]
    return [*DEMO_USERS, *others]


class UserDirectory:
    """Users by id. Example: `directory.create("Luís", Language.PT_BR, Language.EN).user_id`."""

    def __init__(self, storage: Storage, stored: list[User], suffixes: SuffixSource) -> None:
        self._storage = storage
        self._suffixes = suffixes
        known = [*DEMO_USERS, *stored]
        self._users = {user.user_id: user for user in known if user.user_id != GUEST_ID}

    def find(self, user_id: str) -> User | None:
        """The user, or None when unknown or reserved (`guest`)."""
        return self._users.get(user_id)

    def may_connect(self, user_id: str) -> bool:
        """Whether `/ws?user=<user_id>` is allowed: any registered user, never `guest`."""
        return user_id in self._users

    def create(self, display_name: str, comfortable: Language, target: Language) -> User:
        """Make a user with a fresh id and save it (before any of their words can be saved).

        The name is already checked (`routes/users.py`). Raises `ConflictError` only when the
        suffix source keeps repeating ids that are taken.
        """
        user = User(
            user_id=self._free_id(slug_of(display_name)),
            display_name=display_name,
            comfortable_languages=[comfortable],
            target_language=target,
        )
        self._users[user.user_id] = user
        self._storage.save_user(user)
        return user

    def _free_id(self, slug: str) -> str:
        for _ in range(SUFFIX_DRAWS):
            candidate = f"{slug}-{self._suffixes.suffix()}"
            if candidate not in self._users and candidate != GUEST_ID:
                return candidate
        raise ConflictError(f"no free user id for {slug!r} after {SUFFIX_DRAWS} draws; try again")
