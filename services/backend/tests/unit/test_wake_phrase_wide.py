"""The widened wake phrase: greetings, loose names, thanks outside a round, never "mocha"."""

import pytest

from mochi_backend.intelligence.wake_phrase import (
    has_wake_phrase,
    says_mochi,
    without_wake_phrase,
)

GREETINGS = [
    "hi", "hey", "hello", "hey there", "hallo", "oi", "oie", "ola", "olá", "ei", "eai",
    "e aí", "opa", "ok", "okay", "yo", "oh", "ow", "HEY THERE",
]  # fmt: skip
THANKS = ["thanks", "thank you", "thx", "obrigado", "obrigada", "valeu"]
NAMES = [
    "mochi", "moshi", "mochie", "mochy", "mochee", "motchi", "moxi", "moxie", "mo chi",
    "mo-chi", "mo shi", "mochê", "môchi", "mouchi", "mushi", "moji", "Mochi's", "Mochis",
]  # fmt: skip


@pytest.mark.parametrize("greeting", GREETINGS)
@pytest.mark.parametrize("sep", [" ", ", ", "-"])
def test_every_greeting_wakes_with_each_separator(greeting: str, sep: str) -> None:
    assert has_wake_phrase(f"{greeting}{sep}Mochi, hello")
    assert has_wake_phrase(f"{greeting}{sep}Mochi, hello", round_active=True)


@pytest.mark.parametrize("name", NAMES)
def test_every_loose_name_wakes_after_a_greeting(name: str) -> None:
    assert has_wake_phrase(f"Oi {name}, what's the word for fila?")


@pytest.mark.parametrize("thanks", THANKS)
def test_thanks_wakes_only_outside_a_round(thanks: str) -> None:
    assert has_wake_phrase(f"{thanks}, Mochi")
    assert not has_wake_phrase(f"{thanks}, Mochi", round_active=True)


@pytest.mark.parametrize(
    "said",
    [
        "hi mocha", "Oi mocha", "hello, Mocha", "I want a mocha latte", "thanks for the coffee",
        "ok let's go", "my mochi ice cream is melting", "Moji is my cat's name",
        "thank you very much", "Mochi is nice",
    ],
)  # fmt: skip
def test_things_that_must_not_wake(said: str) -> None:
    assert not has_wake_phrase(said)


@pytest.mark.parametrize("said", ["moji", "Moji is my cat", "mocha", "a mocha latte", "mushi"])
def test_bare_name_stays_strict(said: str) -> None:
    assert not says_mochi(said)


@pytest.mark.parametrize(
    ("said", "rest"),
    [
        ("Hey there, Mochi, hello", ", hello"),
        ("e aí Mo-chi what's up", " what's up"),
        ("Thanks Mochi!", "!"),
        ("Hi Mochi's friend", " friend"),
    ],
)
def test_without_wake_phrase_strips_the_wide_phrase(said: str, rest: str) -> None:
    assert without_wake_phrase(said) == rest
