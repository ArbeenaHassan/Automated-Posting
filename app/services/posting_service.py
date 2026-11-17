"""Fans out one message to all platforms concurrently; one failure never stops the others."""
import asyncio
import logging
from datetime import datetime, timezone
from typing import List, Optional

import httpx

from app.config import settings
from app.platforms.base import BasePlatform, PlatformError
from app.platforms.devto import DevToPlatform
from app.platforms.groq import GroqPlatform
from app.schemas import PlatformResult, PostResponse

logger = logging.getLogger("posting")


async def _post_one(platform: BasePlatform, client: httpx.AsyncClient, message: str, url: str) -> PlatformResult:
    if not platform.is_configured():
        return PlatformResult(platform=platform.name, status="failed",
                              error="Credentials not configured (see .env.example).")
    timeout = platform.timeout if isinstance(platform, GroqPlatform) else settings.request_timeout
    try:
        outcome = await asyncio.wait_for(platform.publish(client, message, url), timeout=timeout)
        now = datetime.now(timezone.utc)
        logger.info("%s: success %s", platform.name, outcome.posted_url)
        return PlatformResult(platform=platform.name, status="success", posted_url=outcome.posted_url,
                              public_access=outcome.public_access,
                              date=now.strftime("%Y-%m-%d"), time=now.strftime("%H:%M:%S"))
    except (asyncio.TimeoutError, httpx.TimeoutException):
        error = f"Timed out after {timeout:g}s."
    except PlatformError as exc:
        error = str(exc)
    except httpx.HTTPError as exc:
        error = f"Network error: {exc.__class__.__name__}"
    except (KeyError, ValueError) as exc:
        error = f"Unexpected response format: {exc}"
    except Exception as exc:  # last-resort isolation
        error = f"Unexpected error: {exc.__class__.__name__}"
    logger.warning("%s: failed - %s", platform.name, error)
    return PlatformResult(platform=platform.name, status="failed", error=error)


async def post_everywhere(message: str, url: str, platforms: List[BasePlatform],
                          client: Optional[httpx.AsyncClient] = None) -> PostResponse:
    owns_client = client is None
    client = client or httpx.AsyncClient(timeout=settings.request_timeout)
    try:
        groq = next((p for p in platforms if isinstance(p, GroqPlatform)), None)
        groq_task = asyncio.create_task(_post_one(groq, client, message, url)) if groq else None

        async def run(platform: BasePlatform) -> PlatformResult:
            if platform is groq and groq_task is not None:
                return await groq_task
            if isinstance(platform, DevToPlatform) and groq is not None and groq_task is not None:
                result = await groq_task
                if not groq.is_configured():
                    logger.info("LLM key not set; using fallback title for Dev.to.")
                elif result.status == "failed":
                    logger.warning("LLM title generation failed (%s); using fallback title for Dev.to.", result.error)
                else:
                    logger.info("LLM title generation succeeded; using generated title for Dev.to.")
                platform = DevToPlatform(title=groq.title if result.status == "success" else None)
            return await _post_one(platform, client, message, url)

        results = await asyncio.gather(*(run(p) for p in platforms))
    finally:
        if owns_client:
            await client.aclose()
    return PostResponse(success=any(r.status == "success" and r.platform != GroqPlatform.name for r in results),
                        results=list(results))
