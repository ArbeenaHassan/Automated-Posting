# Automated Multi-Platform Posting System

A FastAPI service that takes **one short message with one CTA link** and publishes it automatically to **5 platforms** through their official APIs, returning a per-platform result.

## Platforms

| Platform | Official API | Auth | Public? |
|---|---|---|---|
| Mastodon | [POST /api/v1/statuses](https://docs.joinmastodon.org/methods/statuses/) | Bearer token (`write:statuses`) | Yes (`visibility=public`) |
| Bluesky | [Creating a post](https://docs.bsky.app/docs/advanced-guides/posts) | Handle + app password | Yes |
| Dev.to | [Forem API – create article](https://developers.forem.com/api/v1) | `api-key` header | Yes (`published=true`) |
| Telegram | [Bot API – sendMessage](https://core.telegram.org/bots/api#sendmessage) | Bot token (bot = admin of public channel) | Yes (public channel) |
| Discord | [Execute Webhook](https://discord.com/developers/docs/resources/webhook#execute-webhook) | Webhook URL | **Yes** – Maybe server members only |

Platform selection is internal (`app/platforms/registry.py`); the request never chooses platforms.

### Optional Groq LLM integration

The five publishing destinations remain unchanged. A sixth result, `Groq (LLM)`,
reports title generation, **not publication**: `posted_url` is `null` and
`public_access` is `false`, even on success. Groq success alone never makes the
overall response successful. `/health` includes Groq configuration presence.

Add these optional variables to your private `.env` (never commit real keys):

```dotenv
GROQ_API_KEY=your-groq-api-key
GROQ_MODEL=openai/gpt-oss-20b
```

One Groq chat-completion request generates a title reused by Dev.to. The title
must be nonblank, at most 80 characters, and contain no URL. Groq has an
8-second total timeout; the other publishing platforms run concurrently.
Dev.to starts its separate posting timeout only after Groq completes.

Missing keys use the existing URL-stripped, 80-character title and log at INFO.
Timeouts, network errors, unsuccessful HTTP responses (including 401/403/429),
and malformed or invalid output produce a failed Groq result and a WARNING
with a safe reason, while Dev.to still attempts publication using its existing
fallback title. Valid output is used with an INFO log. API keys and raw Groq
error bodies are not logged. No additional SDK dependency is required.

## Design

```
POST /posting ──► Pydantic validation ──► posting_service (asyncio.gather)
                                            ├── Mastodon adapter
                                            ├── Bluesky adapter
                                            ├── Dev.to adapter
                                            ├── Telegram adapter
                                            └── Discord adapter
```

- Each adapter implements `BasePlatform.publish()` and returns a normalized outcome.
- Every platform runs **concurrently and independently** with its own timeout. Errors are caught per platform, so one failure never stops the others.
- `success` is `true` if **at least one publishing** platform succeeded; each result carries its own status.
- `posted_url` comes from the API response, or is built only from IDs that the API returns. It is never guessed.
- `date`/`time` are UTC and filled only on success.
- Unconfigured platforms are reported as failed with a clear reason instead of being silently skipped.

## Validation rules

- `message` is required, not empty, and **≤ 200 characters**.
- **Exactly one** link (`http(s)://…` or `www.…`).
- The link must use `http`/`https` and have a valid host.
- Errors return **HTTP 422**:

```json
{"success": false, "errors": [{"field": "message", "message": "Message must contain exactly one CTA link; found 2."}]}
```

## Setup

```bash
git clone <your-repo-url> && cd automated-posting
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # then fill in credentials
uvicorn app.main:app --host 0.0.0.0 --port 4000
```

Swagger UI: http://localhost:4000/docs  ·  Config check: http://localhost:4000/health

### Getting credentials
- **Mastodon:** Preferences → Development → New application (scope `write:statuses`) → copy the access token.
- **Bluesky:** Settings → Privacy and security → App passwords.
- **Dev.to:** Settings → Extensions → DEV Community API Keys.
- **Telegram:** Create a bot with @BotFather, create a **public** channel, and add the bot as an admin. Set `TELEGRAM_CHANNEL_USERNAME=@channel`.
- **Discord:** Channel → Edit → Integrations → Webhooks → New Webhook → Copy URL.

## Sample request

```bash
curl -X POST http://localhost:4000/posting \
  -H "Content-Type: application/json" \
  -d '{"message": "Check out our latest business platform and grow your online visibility. https://example.com"}'
```

## Sample response

Live run on **2026-11-16 at 17:01:12-13 UTC**: `/health` showed all five
platforms configured (`true`), and one `POST /posting` submitted through Swagger
returned HTTP 200 with `success: true` and all five platform statuses `success`.
The health endpoint checks configuration presence, not credential validity;
the publishing response confirms the API outcomes.

This saved evidence predates the optional Groq integration and therefore
contains only the five publishing results, not a live Groq result.

- [Full JSON response](docs/posting-response.json)
- [Swagger response screenshot](docs/swagger-response.png)

### Groq verification round

On 2026-11-16, a second live publishing request again succeeded on all five
publishing platforms. Groq initially returned HTTP 404 because the original
default model was not available to the account; Dev.to successfully used its
fallback title. See the [complete response](docs/posting-response-groq.json).

The default was updated to `openai/gpt-oss-20b`, which was present in the
account's model list. A subsequent **Groq-only** check generated
"Boost Online Visibility with Our New Business Platform"; see the
[live Groq verification](docs/groq-verification.json). No additional public
posts were created by that check.

A full combined run after the correction on **2026-11-16 at 17:46:03-04 UTC**
returned `success: true` with all six integrations successful. See the
[combined live JSON response](docs/posting-response-combined.json).
The public Dev.to API confirmed the published title was
"New Business Platform: Grow Your Online Visibility", demonstrating that the
Groq-generated title was used. Groq itself remains non-public with no post URL.
The screenshots below remain evidence of the original five-platform run.

| Platform | Live post | Screenshot |
|---|---|---|
| Mastodon | [View post](https://mastodon.social/@arbeenahassan/117627189464777389) | [Screenshot](docs/mastodon-live.png) |
| Bluesky | [View post](https://bsky.app/profile/arbeenahassan.bsky.social/post/3n2gywukykd2n) | [Screenshot](docs/bluesky-live.png) |
| Dev.to | [View post](https://dev.to/arbeenahassan/check-out-our-latest-business-platform-and-grow-your-online-visibility-1cal) | [Screenshot](docs/devto-live.png) |
| Telegram | [View post](https://t.me/arbeena_posting_demo/3) | [Screenshot](docs/telegram-live.png) |
| Discord | [View post](https://discord.com/channels/1460235971365699668/1460235972003495988)  | [Screenshot](docs/discord-live.png) |

All five posts were also checked in the browser. The Discord screenshot captures
only the matching message in the authenticated server view; it is not publicly
accessible, and its `posted_url` remains `null` in the saved API response.

## Tests

```bash
python -m pytest tests -q
```
Tests **never publish real posts**. They use fake adapters and `httpx.MockTransport` to cover validation, partial failure, crash isolation, authentication errors, URL parsing, and Bluesky byte-offset link facets.
They also cover Dev.to, Telegram, and Discord success/failure responses, and
Groq title success, missing credentials, timeout/network/HTTP errors, invalid
output, fallback logging, and non-publishing success semantics.

> ⚠️ Only `POST /posting` against a running server with real `.env` credentials creates live posts.

## Security
- Credentials are loaded only from environment variables. `.env` is git-ignored.
- Tokens are never logged or returned in responses.
