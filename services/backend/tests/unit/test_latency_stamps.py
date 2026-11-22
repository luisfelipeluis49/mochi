"""The three latency stamps and the Turns API reader. No network."""

import json

from fastapi.testclient import TestClient

from mochi_backend.app import create_app
from mochi_backend.gateway.agora.rest_client import AgoraTurnsClient
from mochi_backend.gateway.agora.turns_client import (
    markdown_table,
    parse_turns,
    percentile,
)
from mochi_backend.platform.http_client import HttpResponse
from tests.harness import make_harness

URL = "/agora/llm/demo/chat/completions"
KEY = {"x-mochi-key": "k"}


def _lines(harness_logger: object, name: str) -> list[dict[str, object]]:
    lines = harness_logger.lines  # type: ignore[attr-defined]
    return [dict(fields) for event, fields in lines if event == name]


def test_one_turn_logs_all_three_stamps_that_correlate() -> None:
    harness = make_harness(env={"MOCHI_ENABLE_DEV_ROUTES": "true"})
    client = TestClient(create_app(harness.container))
    client.post("/api/sessions/demo/start")
    body = {"messages": [{"role": "user", "content": "I need to adiar my meeting"}], "stream": True}
    assert client.post(URL, json=body, headers=KEY).status_code == 200

    (arrived,) = _lines(harness.logger, "turn_arrived")
    (decided,) = _lines(harness.logger, "arrived_to_decided")
    (first,) = _lines(harness.logger, "reply_first_byte")
    assert arrived["messages"] == 1 and "adiar" not in json.dumps(arrived)
    assert (
        arrived["arrived_monotonic"] == decided["arrived_monotonic"] == first["arrived_monotonic"]
    )
    assert isinstance(decided["arrived_to_decided_ms"], float)
    assert decided["segment_id"] == first["segment_id"] is not None
    assert isinstance(first["arrived_to_first_byte_ms"], float)
    (committed,) = _lines(harness.logger, "turn_committed")
    assert committed["segment_id"] == decided["segment_id"]
    assert isinstance(committed["commit_ms"], float) and "adiar" not in json.dumps(committed)


def test_silent_reply_still_logs_first_byte() -> None:
    harness = make_harness()
    client = TestClient(create_app(harness.container))
    body = {"messages": [{"role": "user", "content": "hello"}], "stream": True}
    client.post(URL, json=body, headers=KEY)  # not capturing: no turn, still a reply
    assert len(_lines(harness.logger, "turn_arrived")) == 1
    assert len(_lines(harness.logger, "reply_first_byte")) == 1


def test_percentile_is_nearest_rank() -> None:
    assert percentile([4, 1, 3, 2], 0.5) == 2
    assert percentile([5], 0.95) == 5
    assert percentile([], 0.5) is None


def test_parse_accepts_dict_and_list_segments() -> None:
    body = json.dumps(
        {
            "turns": [
                {"e2e_latency": 2000, "segmented_latency_ms": {"llm_ttft": 900, "tts_ttfb": 300}},
                {
                    "e2e_latency_ms": 3000,
                    "segmented_latency_ms": [{"name": "llm_ttft", "latency_ms": 1100}],
                },
            ]
        }
    )
    turns = parse_turns(body)
    assert turns[0] == {"e2e_latency_ms": 2000, "llm_ttft": 900, "tts_ttfb": 300}
    table = markdown_table(turns)
    assert "| 2 | 3000 | 1100 | - |" in table and "**p95**" in table


LIVE_SPEAK_REPLY = {  # captured from Agora 2026-11-21 (ids removed): a turn started by /speak
    "agent_id": "A",
    "total_turn_count": 2,
    "pagination": {"is_last_page": True, "page_index": 1, "total_pages": 1},
    "turns": [
        {
            "turn_id": n,
            "start": {"type": "api_speak", "start_at": 1, "metadata": {"transport": "http"}},
            "end": {"type": "ok", "end_at": 2, "metadata": {"playback_duration_ms": 1678}},
            "metrics": {
                "e2e_latency_ms": ms,
                "segmented_latency_ms": [{"latency": ms, "name": "tts_ttfb"}],
            },
        }
        for n, ms in ((1, 358), (2, 331))
    ],
}


def test_parse_live_reply_reads_nested_metrics() -> None:
    turns = parse_turns(json.dumps(LIVE_SPEAK_REPLY))
    assert turns == [
        {"e2e_latency_ms": 358, "tts_ttfb": 358},
        {"e2e_latency_ms": 331, "tts_ttfb": 331},
    ]


class _Getter:
    def __init__(self, reply: HttpResponse) -> None:
        self.reply, self.urls = reply, []  # type: ignore[var-annotated]

    async def get(self, url: str, headers: object, timeout_seconds: float) -> HttpResponse:
        self.urls.append(url)
        return self.reply


async def test_client_gets_turns_and_treats_404_as_empty() -> None:
    ok = _Getter(HttpResponse(200, '[{"e2e_latency": 10}]'))
    assert await AgoraTurnsClient(ok, "APP", "k", "s").turns("ag1") == [{"e2e_latency_ms": 10}]
    assert ok.urls[0].endswith("/projects/APP/agents/ag1/turns")
    gone = _Getter(HttpResponse(404, ""))
    assert await AgoraTurnsClient(gone, "APP", "k", "s").turns("ag1") == []
