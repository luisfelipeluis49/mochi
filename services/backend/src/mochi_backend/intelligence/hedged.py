"""Ask twice when the first answer is slow: one stalled request must not cost the hint."""

import asyncio
from collections.abc import Awaitable, Callable


def _answer[T](task: "asyncio.Future[T | None]") -> T | None:
    """A finished request's answer. A timeout or a cancelled request is no answer.

    Any other error is raised, as it was when there was only one request: it must reach the log.
    """
    if task.cancelled():
        return None
    error = task.exception()
    if error is None:
        return task.result()
    if isinstance(error, TimeoutError):
        return None
    raise error


async def _first_real[T](running: "set[asyncio.Future[T | None]]", seconds: float) -> T | None:
    """The first answer that is not None, waiting at most `seconds` in all."""
    loop = asyncio.get_running_loop()
    ends, waiting = loop.time() + seconds, set(running)
    while waiting and loop.time() < ends:
        done, waiting = await asyncio.wait(
            waiting, timeout=ends - loop.time(), return_when=asyncio.FIRST_COMPLETED
        )
        real = next((a for a in map(_answer, done) if a is not None), None)
        if real is not None:
            return real
    return None


async def first_answer[T](
    ask: Callable[[], Awaitable[T | None]], hedge_after: float, deadline: float
) -> T | None:
    """The first real answer of up to two identical requests, or None at the deadline.

    The second request starts only when the first has not answered after `hedge_after` seconds:
    most slow answers are one stalled connection, and a fresh request beats waiting for it.
    Example: `await first_answer(lambda: model.suggest(request), 1.0, 2.0)`.
    """
    loop = asyncio.get_running_loop()
    ends = loop.time() + deadline
    running: set[asyncio.Future[T | None]] = {asyncio.ensure_future(ask())}
    try:
        await asyncio.wait(running, timeout=min(hedge_after, deadline))
        if not any(task.done() for task in running):
            running.add(asyncio.ensure_future(ask()))
        return await _first_real(running, ends - loop.time())
    finally:
        for task in running:
            task.cancel()
        await asyncio.gather(*running, return_exceptions=True)  # nothing left running or unread
