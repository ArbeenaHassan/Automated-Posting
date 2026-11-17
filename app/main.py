"""FastAPI entry point.  Run: uvicorn app.main:app --host 0.0.0.0 --port 4000"""
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.platforms.registry import get_platforms
from app.schemas import PostRequest, PostResponse
from app.services.posting_service import post_everywhere

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(
    title="Automated Multi-Platform Posting System",
    description="Publishes to five platforms, with optional Groq LLM processing for the Dev.to title. Groq does not publish content.",
    version="1.0.0",
)


@app.exception_handler(RequestValidationError)
async def validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    errors = [{"field": ".".join(str(p) for p in e["loc"] if p != "body"),
               "message": str(e["msg"]).removeprefix("Value error, ")} for e in exc.errors()]
    return JSONResponse(status_code=422, content={"success": False, "errors": errors})


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "platforms": {p.name: p.is_configured() for p in get_platforms()}}


@app.post("/posting", response_model=PostResponse)
async def posting(payload: PostRequest) -> PostResponse:
    return await post_everywhere(payload.message, payload.cta_url, get_platforms())
