# Fixtures

`decisions.json`: test sentences and the decision expected from `decide()` (AGENTS 9.3).
For every case 1-9: at least three sentences that should produce a hint and three near-misses
that should not (`IGNORE`), including both demo sentences.

Fields: `text`; optional `history` (earlier turns, 1 s apart), `hint_turns_ago` (a hint was shown
for the turn that many turns ago), `round_active`, `participants` ("both_learning_en" makes whose-word
unknown), `model` (what the scripted fake model answers). `expect` holds `decision`, `expression`,
`reason`, `target_user_id` and, for SPEAK, `speak_text`.

Run: `make -C services/backend test` (`tests/unit/test_decision_fixtures.py`).
