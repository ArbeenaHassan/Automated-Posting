"""Tests never hit real platforms: adapters are faked or HTTP is mocked."""
import json

import httpx
import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.config import settings
from app.platforms.base import BasePlatform, PlatformError, PublishOutcome
from app.platforms.bluesky import BlueskyPlatform, build_link_facet
from app.platforms.mastodon import MastodonPlatform
from app.platforms.devto import DevToPlatform, make_title
from app.platforms.groq import GroqPlatform
from app.platforms.telegram import TelegramPlatform
from app.platforms.discord import DiscordPlatform
from app.services.posting_service import post_everywhere

client = TestClient(main.app)
VALID = "Check out our latest business platform and grow your online visibility. https://example.com"


class FakeOK(BasePlatform):
    name = "FakeOK"
    def is_configured(self): return True
    async def publish(self, c, m, u): return PublishOutcome("https://fake/post/1", True)


class FakeFail(BasePlatform):
    name = "FakeFail"
    def is_configured(self): return True
    async def publish(self, c, m, u): raise PlatformError("Authentication failed")


class FakeCrash(BasePlatform):
    name = "FakeCrash"
    def is_configured(self): return True
    async def publish(self, c, m, u): raise RuntimeError("boom")


class FakeUnconfigured(FakeOK):
    name = "FakeUnconfigured"
    def is_configured(self): return False


# ---------- validation ----------
@pytest.mark.parametrize("message,expected", [
    ("No link here", "none found"),
    ("Two links https://a.com and https://b.com", "found 2"),
    ("Bad link https://exa mple", "Invalid URL"),
    ("Bad host https://nodot", "Invalid URL"),
    ("x" * 190 + " https://example.com", "200"),
    ("   ", "empty"),
])
def test_invalid_messages(message, expected):
    r = client.post("/posting", json={"message": message})
    assert r.status_code == 422
    assert expected in r.json()["errors"][0]["message"]


def test_missing_message_field():
    assert client.post("/posting", json={}).status_code == 422


# ---------- fan-out & isolation ----------
def test_partial_failure_continues(monkeypatch):
    monkeypatch.setattr(main, "get_platforms", lambda: [FakeOK(), FakeFail(), FakeCrash(), FakeUnconfigured()])
    r = client.post("/posting", json={"message": VALID})
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    by = {x["platform"]: x for x in body["results"]}
    assert by["FakeOK"]["status"] == "success" and by["FakeOK"]["date"] and by["FakeOK"]["time"]
    assert by["FakeFail"]["error"] == "Authentication failed" and by["FakeFail"]["date"] is None
    assert "RuntimeError" in by["FakeCrash"]["error"]
    assert "not configured" in by["FakeUnconfigured"]["error"]


def test_all_fail_success_false(monkeypatch):
    monkeypatch.setattr(main, "get_platforms", lambda: [FakeFail(), FakeCrash()])
    assert client.post("/posting", json={"message": VALID}).json()["success"] is False


# ---------- adapter behaviour with mocked HTTP ----------
@pytest.mark.anyio
async def test_mastodon_adapter_parses_url(monkeypatch):
    monkeypatch.setattr(settings, "mastodon_access_token", "t")
    def handler(req: httpx.Request):
        assert req.headers["Authorization"] == "Bearer t"
        return httpx.Response(200, json={"url": "https://mastodon.social/@me/1", "visibility": "public"})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
        res = await post_everywhere(VALID, "https://example.com", [MastodonPlatform()], client=c)
    assert res.results[0].posted_url == "https://mastodon.social/@me/1" and res.results[0].public_access


@pytest.mark.anyio
async def test_mastodon_auth_failure(monkeypatch):
    monkeypatch.setattr(settings, "mastodon_access_token", "bad")
    async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda r: httpx.Response(401, json={"error": "invalid token"}))) as c:
        res = await post_everywhere(VALID, "https://example.com", [MastodonPlatform()], client=c)
    assert res.results[0].status == "failed" and "Authentication failed" in res.results[0].error


@pytest.mark.anyio
async def test_bluesky_adapter_builds_url_and_facet(monkeypatch):
    monkeypatch.setattr(settings, "bluesky_handle", "me.bsky.social")
    monkeypatch.setattr(settings, "bluesky_app_password", "pw")
    def handler(req: httpx.Request):
        if req.url.path.endswith("createSession"):
            return httpx.Response(200, json={"did": "did:plc:x", "accessJwt": "j", "handle": "me.bsky.social"})
        rec = json.loads(req.content)["record"]
        assert rec["facets"][0]["features"][0]["uri"] == "https://example.com"
        return httpx.Response(200, json={"uri": "at://did:plc:x/app.bsky.feed.post/abc", "cid": "c"})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
        res = await post_everywhere(VALID, "https://example.com", [BlueskyPlatform()], client=c)
    assert res.results[0].posted_url == "https://bsky.app/profile/me.bsky.social/post/abc"


def test_facet_uses_byte_offsets():
    text = "héllo 🚀 https://example.com"
    f = build_link_facet(text, "https://example.com")[0]["index"]
    assert text.encode()[f["byteStart"]:f["byteEnd"]].decode() == "https://example.com"


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
@pytest.mark.parametrize("failure", [
    "timeout", "network", "401", "403", "429", "empty", "malformed",
    "blank", "long", "url", "missing-key",
])
async def test_llm_failure_preserves_devto_post(monkeypatch, caplog, failure):
    monkeypatch.setattr(settings, "groq_api_key", "" if failure == "missing-key" else "secret-test-key")
    monkeypatch.setattr(settings, "devto_api_key", "dev-key")
    caplog.set_level("INFO", logger="posting")
    titles = []
    def handler(req: httpx.Request):
        if req.url.host == "dev.to":
            titles.append(json.loads(req.content)["article"]["title"])
            return httpx.Response(200, json={"url": "https://dev.to/me/post", "published": True})
        assert req.extensions["timeout"]["read"] == 8
        if failure == "timeout":
            raise httpx.ReadTimeout("secret-test-key", request=req)
        if failure == "network":
            raise httpx.ConnectError("secret-test-key", request=req)
        if failure.isdigit():
            return httpx.Response(int(failure), text="secret-test-key")
        if failure == "empty":
            return httpx.Response(200, content=b"")
        if failure == "malformed":
            return httpx.Response(200, json={"choices": []})
        content = {"blank": " ", "long": "x" * 81, "url": "Visit example.com"}[failure]
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
        result = await post_everywhere(VALID, "https://example.com",
                                      [DevToPlatform(), GroqPlatform()], client=c)
    assert titles == [make_title(VALID)]
    assert result.success and result.results[0].status == "success"
    assert result.results[1].status == "failed"
    if failure == "missing-key":
        assert any(r.levelname == "INFO" and "LLM key not set" in r.message for r in caplog.records)
    else:
        assert any(r.levelname == "WARNING" and "using fallback title for Dev.to" in r.message
                   for r in caplog.records)
    assert "secret-test-key" not in caplog.text


@pytest.mark.anyio
async def test_llm_success_reuses_title_and_does_not_count_as_publishing(monkeypatch, caplog):
    monkeypatch.setattr(settings, "groq_api_key", "secret-test-key")
    monkeypatch.setattr(settings, "devto_api_key", "dev-key")
    caplog.set_level("INFO", logger="posting")
    groq_calls = []
    def handler(req: httpx.Request):
        if req.url.host == "api.groq.com":
            groq_calls.append(req)
            return httpx.Response(200, json={"choices": [{"message": {"content": "Grow Your Business"}}]})
        assert json.loads(req.content)["article"]["title"] == "Grow Your Business"
        return httpx.Response(200, json={"url": "https://dev.to/me/post", "published": True})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
        result = await post_everywhere(VALID, "https://example.com",
                                      [DevToPlatform(), GroqPlatform()], client=c)
        assert len(groq_calls) == 1
        monkeypatch.setattr(settings, "devto_api_key", "")
        no_post = await post_everywhere(VALID, "https://example.com",
                                       [DevToPlatform(), GroqPlatform()], client=c)
    assert result.success
    groq_result = result.results[1]
    assert groq_result.status == "success"
    assert groq_result.posted_url is None and not groq_result.public_access
    assert not no_post.success and no_post.results[1].status == "success"
    assert "using generated title for Dev.to" in caplog.text


@pytest.mark.anyio
@pytest.mark.parametrize("adapter", [DevToPlatform, TelegramPlatform, DiscordPlatform])
@pytest.mark.parametrize("succeeds", [True, False])
async def test_remaining_adapters_success_and_failure(monkeypatch, adapter, succeeds):
    monkeypatch.setattr(settings, "devto_api_key", "test-dev-key")
    monkeypatch.setattr(settings, "telegram_bot_token", "test-bot-token")
    monkeypatch.setattr(settings, "telegram_channel_username", "@demo")
    monkeypatch.setattr(settings, "discord_webhook_url", "https://discord.com/api/webhooks/test/token")
    def handler(req: httpx.Request):
        body = json.loads(req.content)
        if adapter is DevToPlatform:
            assert req.headers["api-key"] == "test-dev-key"
            assert body["article"] == {
                "title": make_title(VALID), "body_markdown": VALID, "published": True,
            }
            return (httpx.Response(200, json={"url": "https://dev.to/me/post", "published": True})
                    if succeeds else httpx.Response(401, json={"error": "Unauthorized"}))
        if adapter is TelegramPlatform:
            assert req.url.path == "/bottest-bot-token/sendMessage"
            assert body == {"chat_id": "@demo", "text": VALID}
            return (httpx.Response(200, json={"ok": True, "result": {
                "message_id": 7, "chat": {"username": "demo"},
            }}) if succeeds else httpx.Response(403, json={"ok": False, "description": "Forbidden"}))
        assert req.url.params["wait"] == "true"
        assert body == {"content": VALID}
        return (httpx.Response(200, json={"guild_id": "1", "channel_id": "2", "id": "3"})
                if succeeds else httpx.Response(429, json={"message": "Rate limited"}))
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
        result = await post_everywhere(VALID, "https://example.com", [adapter()], client=c)
    item = result.results[0]
    assert result.success is succeeds
    assert item.status == ("success" if succeeds else "failed")
    if succeeds:
        expected_urls = {
            DevToPlatform: "https://dev.to/me/post",
            TelegramPlatform: "https://t.me/demo/7",
            DiscordPlatform: "https://discord.com/channels/1/2/3",
        }
        assert item.posted_url == expected_urls[adapter]
        assert item.public_access is (adapter is not DiscordPlatform)
    else:
        assert item.error and item.posted_url is None
        assert item.date is None and item.time is None
