"""Who Papear knows: the demo session and device, the seeded people, and the people added since.

The two demo people (AGENTS 2) are always seeded, so the walkthrough and the tests keep working.
A company adds its own through `POST /api/companies/{id}/members` (DECISIONS D-45).
"""

from mochi_backend.storage.port import voice_key
from mochi_contracts import Company, Language, Member, MemberRole, Participant, User

SESSION_ID = "demo"
HOME_DEVICE_ID = "home_pi_01"
DEMO_PARTICIPANTS: list[Participant] = [
    Participant(user_id="ana", comfortable_languages=[Language.PT_BR], target_language=Language.EN),
    Participant(user_id="ben", comfortable_languages=[Language.EN], target_language=Language.PT_BR),
]
USER_IDS: list[str] = [p.user_id for p in DEMO_PARTICIPANTS]
# The users seeded into the database (names as people say them; voices are matched to them).
DEMO_USERS: list[User] = [
    User(
        user_id=p.user_id,
        display_name=p.user_id.capitalize(),
        comfortable_languages=p.comfortable_languages,
        target_language=p.target_language,
    )
    for p in DEMO_PARTICIPANTS
]
# One company per deployment for now; every table carries `company_id` so that can change.
DEMO_COMPANY = Company(company_id="demo", name="Papear Demo")
# Someone has to be able to open the team view: the first demo person is the administrator.
DEMO_MEMBERS: list[Member] = [
    Member(
        company_id=DEMO_COMPANY.company_id,
        user_id=user.user_id,
        role=MemberRole.ADMIN if index == 0 else MemberRole.MEMBER,
    )
    for index, user in enumerate(DEMO_USERS)
]


def as_participant(user: User) -> Participant:
    """The session's view of a person. Example: `as_participant(DEMO_USERS[0]).user_id` is "ana"."""
    return Participant(
        user_id=user.user_id,
        comfortable_languages=user.comfortable_languages,
        target_language=user.target_language,
    )


class Roster:
    """The people this backend knows, in the order they were added.

    Example: `Roster(DEMO_USERS).knows("ana")` is True. Held in memory; storage keeps the copy.
    """

    def __init__(self, users: list[User] | None = None) -> None:
        self._users: dict[str, User] = {u.user_id: u for u in users or DEMO_USERS}

    def users(self) -> list[User]:
        """Everyone, oldest first."""
        return list(self._users.values())

    def user_ids(self) -> list[str]:
        """Everyone's id. Example: `["ana", "ben"]`."""
        return list(self._users)

    def knows(self, user_id: str | None) -> bool:
        """True for a known id. Example: `roster.knows("zed")` is False."""
        return user_id in self._users

    def user(self, user_id: str) -> User | None:
        """The person with this id, or None."""
        return self._users.get(user_id)

    def participants(self) -> list[Participant]:
        """Everyone, as a session sees them."""
        return [as_participant(user) for user in self._users.values()]

    def named(self, name: str | None) -> str | None:
        """The `user_id` whose display name is this (any case), or None.

        A voice is registered under the name a person says; this ties it to the person.
        Example: `roster.named(" ana ")` is `"ana"`.
        """
        wanted = voice_key(name or "")
        found = (u.user_id for u in self._users.values() if voice_key(u.display_name) == wanted)
        return next(found, None)

    def add(self, user: User) -> None:
        """Add a person, or replace the one with the same id."""
        self._users[user.user_id] = user
