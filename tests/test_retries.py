import asyncio
import io
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from telegram.error import BadRequest, NetworkError, RetryAfter, TimedOut

from emojigif.bot import download_telegram, download_url, report_failure, send_document
from emojigif.network import RequestFailure, request_with_retry


def timeout(cause):
    error = TimedOut()
    error.__cause__ = cause
    return error


def test_get_file_recovers_after_timeout(tmp_path):
    get_file = AsyncMock(
        side_effect=[TimedOut(), SimpleNamespace(file_size=1, file_path="https://example.com/file")]
    )
    context = SimpleNamespace(
        bot=SimpleNamespace(get_file=get_file),
        application=SimpleNamespace(bot_data={"http": None}),
    )
    with (
        patch("emojigif.network.asyncio.sleep", new_callable=AsyncMock) as sleep,
        patch("emojigif.bot.download_url", new_callable=AsyncMock) as download,
    ):
        asyncio.run(download_telegram(context, "id", tmp_path / "source"))
    assert get_file.await_count == 2
    assert download.await_count == 1
    sleep.assert_awaited_once_with(1)


def test_retries_are_bounded_and_logs_do_not_expose_urls(caplog):
    private_url = "https://example.com/private-token"
    action = AsyncMock(side_effect=NetworkError(private_url))
    with patch("emojigif.network.asyncio.sleep", new_callable=AsyncMock) as sleep:
        with pytest.raises(RequestFailure) as failure:
            asyncio.run(request_with_retry("get_file", action))
    assert action.await_count == 3
    assert [call.args[0] for call in sleep.await_args_list] == [1, 2]
    message = SimpleNamespace(reply_text=AsyncMock())
    asyncio.run(report_failure(message, failure.value))
    assert "get_file" in caplog.text
    assert private_url not in caplog.text
    assert private_url not in message.reply_text.call_args.args[0]


@pytest.mark.parametrize("error", [BadRequest("invalid"), RetryAfter(61)])
def test_permanent_errors_and_long_rate_limits_are_not_retried(error):
    action = AsyncMock(side_effect=error)
    with patch("emojigif.network.asyncio.sleep", new_callable=AsyncMock) as sleep:
        with pytest.raises(RequestFailure):
            asyncio.run(request_with_retry("get_file", action))
    assert action.await_count == 1
    sleep.assert_not_awaited()


@pytest.mark.parametrize(
    "error",
    [
        timeout(httpx.ConnectTimeout("private")),
        timeout(httpx.PoolTimeout("private")),
        RetryAfter(timedelta(seconds=2)),
    ],
)
def test_upload_retries_before_delivery_and_rewinds_file(error):
    bodies = []

    async def reply_document(**kwargs):
        bodies.append(kwargs["document"].read())
        if len(bodies) == 1:
            raise error

    with patch("emojigif.network.asyncio.sleep", new_callable=AsyncMock):
        asyncio.run(
            send_document(
                SimpleNamespace(reply_document=reply_document), io.BytesIO(b"zip"), "e.zip"
            )
        )
    assert bodies == [b"zip", b"zip"]


@pytest.mark.parametrize(
    "error",
    [
        timeout(httpx.ReadTimeout("private")),
        timeout(httpx.WriteTimeout("private")),
        TimedOut(),
        NetworkError("private"),
    ],
)
def test_uncertain_delivery_is_not_repeated(error):
    message = SimpleNamespace(reply_document=AsyncMock(side_effect=error), reply_text=AsyncMock())
    with pytest.raises(RequestFailure) as failure:
        asyncio.run(send_document(message, io.BytesIO(b"zip"), "e.zip"))
    assert message.reply_document.await_count == 1
    assert failure.value.delivery_uncertain
    asyncio.run(report_failure(message, failure.value))
    assert "may already have arrived" in message.reply_text.call_args.args[0]


def test_partial_download_is_replaced_on_retry(tmp_path):
    class InterruptedStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b"x" * (64 * 1024)
            raise httpx.ReadTimeout("interrupted")

    calls = 0

    def respond(request):
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(200, stream=InterruptedStream())
        return httpx.Response(200, content=b"complete")

    path = tmp_path / "source"

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            assert await download_url(client, "https://example.com/file", path)

    with patch("emojigif.network.asyncio.sleep", new_callable=AsyncMock):
        asyncio.run(run())
    assert calls == 2
    assert path.read_bytes() == b"complete"


@pytest.mark.parametrize("status, expected_calls", [(503, 2), (404, 1), (403, 1)])
def test_download_status_retry_policy(tmp_path, status, expected_calls):
    calls = 0

    def respond(request):
        nonlocal calls
        calls += 1
        return httpx.Response(status if calls == 1 else 200, content=b"image")

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            result = await download_url(client, "https://example.com/file", tmp_path / "source")
            assert result is (status != 404)

    with patch("emojigif.network.asyncio.sleep", new_callable=AsyncMock):
        if status == 403:
            with pytest.raises(RequestFailure):
                asyncio.run(run())
        else:
            asyncio.run(run())
    assert calls == expected_calls


def test_cancellation_is_not_retried():
    action = AsyncMock(side_effect=asyncio.CancelledError())
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(request_with_retry("download", action))
    assert action.await_count == 1
