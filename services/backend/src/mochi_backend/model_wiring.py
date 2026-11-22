"""Part of the composition root: the models beside the hint judge and Mochi's own voice.

Kept apart from `composition.py` only for its size; nothing else constructs these adapters.
"""

from mochi_backend.intelligence.json_chat import JsonChat, JsonChatConfig
from mochi_backend.intelligence.openai_coach_model import OpenAiCoachModel
from mochi_backend.intelligence.openai_explain_model import OpenAiExplainModel
from mochi_backend.intelligence.openai_phrase_model import OpenAiPhraseModel
from mochi_backend.intelligence.service import Intelligence
from mochi_backend.platform.http_client import HttpxClient
from mochi_backend.platform.json_logging import EventLogger
from mochi_backend.settings import Settings


def look_beyond_the_word(brain: Intelligence, settings: Settings, logger: EventLogger) -> None:
    """Give the brain the models that look at more than the stuck word: one explains an
    idiom or a term to the people listening (D-53), one reads a person's sentences after the
    session (D-54). Example: `look_beyond_the_word(brain, settings, logger)`."""
    if settings.mochi_explain_terms:
        http = HttpxClient()
        chat = JsonChat(http, _explain_model(settings), "explain", logger).warming(http)
        brain.explain_with(OpenAiExplainModel(chat))
    if settings.mochi_suggest_phrases:
        http = HttpxClient()
        chat = JsonChat(http, _explain_model(settings), "phrase", logger).warming(http)
        brain.phrase_with(OpenAiPhraseModel(chat))
    if settings.mochi_speech_reports:
        chat = JsonChat(HttpxClient(), _coach_model(settings), "coach", logger)
        brain.coach_with(OpenAiCoachModel(chat))


def _explain_model(settings: Settings) -> JsonChatConfig:
    """The hint judge's model: an explanation has the same second or two to arrive in."""
    return JsonChatConfig(
        base_url=settings.mochi_model_base_url,
        model_name=settings.mochi_model_name,
        api_key=settings.model_api_key,
        timeout_seconds=settings.mochi_decide_timeout_seconds,
        reasoning_effort=settings.mochi_model_reasoning_effort,
    )


def _coach_model(settings: Settings) -> JsonChatConfig:
    """The model that writes reports: nobody waits for it, so it may think a little."""
    thinking = "low" if settings.mochi_model_reasoning_effort else ""
    return JsonChatConfig(
        base_url=settings.mochi_model_base_url,
        model_name=settings.mochi_report_model_name or settings.mochi_model_name,
        api_key=settings.model_api_key,
        timeout_seconds=settings.mochi_report_timeout_seconds,
        reasoning_effort=settings.mochi_report_reasoning_effort or thinking,
    )
