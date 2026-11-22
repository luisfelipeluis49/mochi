"""The live transcript: each finished sentence goes to the people in the session as it is said,
with what Mochi noticed in it (DECISIONS D-51 to D-53).

A line is published when its turn is committed, never before: a turn that is dropped (Stop, a
newer request from Agora) must leave no trace. An idiom or a technical term is looked for
afterwards, off the turn's path, and the line is sent again with the explanation when one comes.
"""

import asyncio
import json

from mochi_backend.gateway.core import GatewayCore
from mochi_backend.gateway.device_commands import DeviceCommand
from mochi_contracts import (
    Decision,
    DecisionKind,
    EventType,
    Hint,
    MarkKind,
    Reason,
    SessionContext,
    TranscriptLine,
    TranscriptMark,
    Turn,
)

CAPTION_LIMIT = 200  # characters of a sentence that go to the device's small screen


def switch_marks(hint: Hint | None) -> list[TranscriptMark]:
    """The mark for a code switch: the word that was said in the other language, and the word
    of the language being spoken. Empty for any other hint.

    Example: the hint "postpone" (meaning "adiar", reason code_switch) -> adiar -> postpone.
    """
    if hint is None or hint.reason is not Reason.CODE_SWITCH or not hint.meaning:
        return []
    return [TranscriptMark(kind=MarkKind.CODE_SWITCH, text=hint.meaning, gloss=hint.expression)]


def explain_card(mark: TranscriptMark) -> str:
    """What the device shows for an explained idiom or term, as JSON.

    Example: `{"word": "circle back", "meaning": "voltar ao assunto depois", "plain": "talk
    about it again later", "kind": "idiom"}`.
    """
    card = {"word": mark.text, "meaning": mark.gloss, "plain": mark.plain, "kind": mark.kind.value}
    return json.dumps(card, ensure_ascii=False)


class LiveTranscript:
    """Example: `await transcript.show(turn, marks)` inside the turn's commit, then
    `transcript.explain_later(turn, context, decision)` once it is done."""

    def __init__(self, core: GatewayCore, *, lines: bool = True, explains: bool = True) -> None:
        self._core = core
        self._lines = lines  # MOCHI_LIVE_TRANSCRIPT
        self._explains = explains  # MOCHI_EXPLAIN_TERMS
        self._looking: set[asyncio.Task[None]] = set()  # explanations still being worked out

    def _who(self, user_id: str | None) -> str | None:
        person = self._core.store.roster.user(user_id or "")
        return person.display_name if person else None

    def _caption(self, turn: Turn) -> DeviceCommand:
        card = {"who": self._who(turn.speaker_user_id), "text": turn.text[-CAPTION_LIMIT:]}
        return self._command("caption", json.dumps(card, ensure_ascii=False))

    def _command(self, kind: str, value: str) -> DeviceCommand:
        core = self._core
        return DeviceCommand(
            command_id=core.ids.new("cmd"), kind=kind, value=value, at=core.clock.now()
        )

    async def show(self, turn: Turn, marks: list[TranscriptMark], again: bool = False) -> None:
        """Publish the sentence to the session, and hand it to the device as a caption.

        `again`: the line was shown before and only its marks changed, so the device needs no
        second caption. Call it while holding the commit lock. Not in a review: what one person
        says to Mochi on their phone was heard by nobody else, so it is shown to nobody else.
        """
        if not self._lines or self._core.store.reviewer is not None:
            return
        line = TranscriptLine(
            utterance_id=turn.segment_id,
            user_id=turn.speaker_user_id,
            text=turn.text,
            at=turn.received_at,
            marks=marks,
        )
        await self._core.hub.publish(EventType.TRANSCRIPT_LINE, line)
        if not again:
            self._core.store.queue([self._caption(turn)])

    def explain_later(
        self, turn: Turn, context: SessionContext, decision: Decision, generation: int
    ) -> None:
        """Look for an idiom or a technical term in a sentence that needed nothing else, without
        making anything wait. A sentence that got a hint or an answer is left alone.

        `generation`: the store's when the turn began. Read now instead, a Stop and a new Start
        in between would let the old sentence's explanation into the new session.
        """
        if not self._explains or decision.decision is not DecisionKind.IGNORE:
            return
        looking = asyncio.ensure_future(self._explain(turn, context, generation))
        self._looking.add(looking)
        looking.add_done_callback(self._looking.discard)

    async def settle(self) -> None:
        """Wait for the explanations being worked out (tests, and a clean shutdown)."""
        await asyncio.gather(*list(self._looking), return_exceptions=True)

    async def _explain(self, turn: Turn, context: SessionContext, generation: int) -> None:
        try:
            mark = await self._core.intelligence.explain(turn, context)
            await self._explained(turn, mark, generation)
        except Exception as error:  # an explanation that fails must cost nothing else
            self._core.logger.log(
                "explain_failed", {"segment_id": turn.segment_id, "error": repr(error)}
            )

    async def _explained(self, turn: Turn, mark: TranscriptMark | None, generation: int) -> None:
        if mark is None:
            return
        async with self._core.commit:  # not in the middle of a turn, a Stop or a Reset
            await self._show_explained(turn, mark, generation)

    async def _show_explained(self, turn: Turn, mark: TranscriptMark, generation: int) -> None:
        store = self._core.store
        if generation != store.generation or not store.capturing:
            return  # the session it belonged to is over
        kept = self._core.journal.noticed(turn.segment_id, mark)
        await self.show(turn, kept.marks if kept else [mark], again=True)
        if self._core.live_hint.current is None:  # a stuck speaker's word is never covered
            store.queue([self._command("explain", explain_card(mark))])
        said = {"segment_id": turn.segment_id, "kind": mark.kind.value, "expression": mark.text}
        self._core.logger.log("explained", said)
