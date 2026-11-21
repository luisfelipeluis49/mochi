"""Speech-to-text sometimes writes its own prompt into the transcript; that part is removed."""

from fastapi.testclient import TestClient

from mochi_backend.app import create_app
from mochi_backend.composition import vocabulary
from mochi_backend.gateway.prompt_echo import without_prompt_echo
from mochi_backend.settings import load_settings
from tests.harness import make_harness

WORDS = vocabulary(load_settings({"MOCHI_AGORA_MODE": "fake"}))
PROMPT = load_settings({"MOCHI_AGORA_MODE": "fake"}).mochi_asr_prompt + " Words that may come up:"
HEARD_LIVE = (
    "Como você falar Mochi, adiar, postpone, guarda-chuva, umbrella, recibo, receipt, fila, queue, "
    "mala, suitcase, saca-rolhas, corkscrew, geladeira, fridge, chave, key, atrasar, delay, "
    "reunião, meeting. Esqueci a palavra. Limpar em inglês?"
)


def test_the_word_list_seen_in_a_live_transcript_is_removed() -> None:
    kept = without_prompt_echo(HEARD_LIVE, PROMPT, WORDS)
    assert kept == "Como você falar Esqueci a palavra. Limpar em inglês?"


def test_words_people_really_say_are_left_alone() -> None:
    for said in (
        "I forgot my guarda-chuva at the office.",
        "Oi Mochi, como se diz fila em inglês?",
        "Is it queue, or fila? I need my umbrella and my key.",
        "Did you watch the match yesterday?",
    ):
        assert without_prompt_echo(said, PROMPT, WORDS) == said


def test_the_instruction_itself_is_removed_too() -> None:
    heard = "Write every word in the language it was spoken in; never translate. Bom dia!"
    assert without_prompt_echo(heard, PROMPT, WORDS) == "Bom dia!"
    assert (
        without_prompt_echo("Words that may come up: fila, queue, mala, key.", PROMPT, WORDS) == ""
    )


def test_an_echoed_list_never_reaches_the_hint_rules() -> None:
    """Without this, "adiar" in the pasted list would look like a word the person needed."""
    harness = make_harness()
    client = TestClient(create_app(harness.container))
    client.post("/api/sessions/demo/start")
    body = {"messages": [{"role": "user", "content": HEARD_LIVE}]}
    reply = client.post("/agora/llm/demo/chat/completions", json=body, headers={"x-mochi-key": "k"})
    assert reply.status_code == 200
    turns = [fields["text"] for name, fields in harness.logger.lines if name == "turn"]
    assert turns == ["Como você falar Esqueci a palavra. Limpar em inglês?"]
    assert "ears_prompt_echo" in harness.logger.names()
    assert harness.container.core.store.hints == []


def test_the_lexicon_can_be_left_out_of_what_the_ears_are_told() -> None:
    """Named words are also heard in unclear audio: faint background speech came back as
    "People don't like to adiar reuniões" and got a hint (DECISIONS D-36)."""
    named = vocabulary(load_settings({"MOCHI_AGORA_MODE": "fake"}))
    assert "adiar" in named and "Mochi" in named  # the default is unchanged
    plain = load_settings({"MOCHI_AGORA_MODE": "fake", "MOCHI_ASR_LEXICON_WORDS": "false"})
    assert vocabulary(plain) == ("Mochi",)
