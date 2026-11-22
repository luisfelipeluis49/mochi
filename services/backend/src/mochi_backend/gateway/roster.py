"""The fixed demo: one session, two people, one device (AGENTS 2 and 6.4)."""

from mochi_contracts import Language, Participant, User

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
# The second person in a web session (D-42). Reserved: never a user anyone can be. Seeded with the
# demo users so a guest's learning events satisfy the database's foreign key; the languages stored
# here are irrelevant, each session's participant carries the real ones.
GUEST_ID = "guest"
GUEST_USER = User(
    user_id=GUEST_ID,
    display_name="Guest",
    comfortable_languages=[Language.EN],
    target_language=Language.PT_BR,
)
