"""Bounded network retries without logging credential-bearing exception messages."""

import asyncio
import logging
from collections.abc import Awaitable, Callable

import httpx
from telegram.error import NetworkError, RetryAfter, TelegramError, TimedOut

LOG = logging.getLogger(__name__)
ATTEMPTS = 3


class RequestFailure(Exception):
    def __init__(self, operation: str, error: Exception, delivery_uncertain: bool = False):
        super().__init__(f"{operation}: {type(error).__name__}")
        self.operation = operation
        self.error = error
        self.delivery_uncertain = delivery_uncertain


def transient(error: Exception) -> bool:
    # BadRequest inherits NetworkError, but retrying an invalid request cannot help.
    return (
        isinstance(error, (TimedOut, httpx.TransportError))
        or type(error) is NetworkError
        or (
            isinstance(error, httpx.HTTPStatusError)
            and error.response.status_code in {500, 502, 503, 504}
        )
    )


async def request_with_retry[T](
    operation: str, action: Callable[[], Awaitable[T]], *, safe_to_repeat: bool = True
) -> T:
    for attempt in range(ATTEMPTS):
        try:
            return await action()
        except (TelegramError, httpx.HTTPError) as error:
            before_send = isinstance(
                error.__cause__, (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout)
            )
            uncertain = not safe_to_repeat and transient(error) and not before_send
            delay = 2**attempt
            if isinstance(error, RetryAfter):
                value = error.retry_after
                delay = value.total_seconds() if hasattr(value, "total_seconds") else value
                retry = delay <= 60
                delay += 0.1
            else:
                retry = transient(error) and (safe_to_repeat or before_send)
            if not retry or attempt == ATTEMPTS - 1:
                raise RequestFailure(operation, error, uncertain) from error
            LOG.warning(
                "%s: %s (%s); retry %d/%d in %.1fs",
                operation,
                type(error).__name__,
                type(error.__cause__).__name__ if error.__cause__ else "no transport detail",
                attempt + 1,
                ATTEMPTS - 1,
                delay,
            )
            await asyncio.sleep(delay)
    raise AssertionError("Retry loop exhausted without returning or raising")
