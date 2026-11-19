"""The fixed demo: one session, two people, one device (AGENTS 2 and 6.4)."""

from mochi_contracts import Language, Participant

SESSION_ID = "demo"
HOME_DEVICE_ID = "home_pi_01"
DEMO_PARTICIPANTS: list[Participant] = [
    Participant(user_id="ana", comfortable_languages=[Language.PT_BR], target_language=Language.EN),
    Participant(user_id="ben", comfortable_languages=[Language.EN], target_language=Language.PT_BR),
]
USER_IDS: list[str] = [p.user_id for p in DEMO_PARTICIPANTS]
