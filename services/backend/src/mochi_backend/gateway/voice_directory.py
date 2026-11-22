"""The voices Mochi has learned and whose they are. Biometric data: only device-key routes use it.

The Pi keeps its own copy (`data/voices.json`) and, after learning a voice, sends the vector
here (`PUT .../voiceprint`). At each session start it adds the voices it lacks from
`GET .../voices`, so a replaced or reflashed Pi gets its voices back. A voice that was only linked
(`POST .../voices`) has no vector yet. Each voice name is linked to a user. Reads come from memory;
writes are queued to storage by `WriteBehindStorage`.
"""

import math

from mochi_backend.gateway.roster import Roster
from mochi_backend.storage.port import Storage, voice_key
from mochi_contracts import VoiceLanguage, VoiceprintUpload, VoiceProfile

MAX_VECTOR_LENGTH = 1024  # the speaker model gives 192 numbers; this only stops runaway bodies


class InvalidVoiceprintError(ValueError):
    """The vector is empty, too long or has a number that is not finite."""


def check_voiceprint(vector: list[float]) -> None:
    """Raise `InvalidVoiceprintError` unless it is 1..1024 finite numbers.

    Example: `check_voiceprint([0.1, -0.2])` passes; `check_voiceprint([float("nan")])` raises.
    """
    if not 0 < len(vector) <= MAX_VECTOR_LENGTH:
        raise InvalidVoiceprintError(
            f"voiceprint has {len(vector)} numbers; expected between 1 and {MAX_VECTOR_LENGTH}"
        )
    if not all(math.isfinite(number) for number in vector):
        raise InvalidVoiceprintError("voiceprint has a number that is not finite (NaN or inf)")


class VoiceDirectory:
    """Voices by name. Example: `directory.link("Ana", "pt")` then `directory.owner_of("ana")`.

    `voices` are the ones storage held at startup (read once by `storage_for`)."""

    def __init__(self, storage: Storage, voices: list[VoiceProfile], roster: Roster) -> None:
        self._storage = storage
        self._roster = roster
        self._voices = {voice_key(v.name): v for v in voices}

    def all(self) -> list[VoiceProfile]:
        """Every learned voice, by name."""
        return sorted(self._voices.values(), key=lambda voice: voice_key(voice.name))

    def owner_of(self, name: str) -> str | None:
        """The `user_id` whose display name is this voice name (any case), or None."""
        return self._roster.named(name)

    def link(self, name: str, language: VoiceLanguage) -> VoiceProfile:
        """A voice was learned: remember who it belongs to. An earlier vector is kept."""
        before = self._voices.get(voice_key(name))
        voice = VoiceProfile(
            name=name,
            user_id=self.owner_of(name),
            language=language,
            voiceprint=before.voiceprint if before else None,
            saved=before.saved if before else None,
        )
        return self._keep(voice)

    def store_vector(self, name: str, upload: VoiceprintUpload) -> VoiceProfile:
        """Keep the voiceprint the device sends. Raises `InvalidVoiceprintError` on a bad one."""
        check_voiceprint(upload.voiceprint)
        voice = VoiceProfile(
            name=name,
            user_id=self.owner_of(name),
            language=upload.language,
            voiceprint=upload.voiceprint,
            saved=upload.saved,
        )
        return self._keep(voice)

    def forget(self, name: str) -> bool:
        """Delete the voice and its vector here and in storage. False when it was not there."""
        known = self._voices.pop(voice_key(name), None) is not None
        self._storage.delete_voice(name)
        return known

    def _keep(self, voice: VoiceProfile) -> VoiceProfile:
        self._voices[voice_key(voice.name)] = voice
        self._storage.save_voice(voice)
        return voice
