"""FastAPI app: timing middleware, one friendly error boundary, API + built frontend."""

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app import faults, telemetry
from app.access import Forbidden, Unauthenticated, Withdrawn
from app.api.routes import router
from app.config import get_settings
from app.db import session as db_session
from app.db.crypto import fernet
from app.db.models import TimingRecord
from app.profile import get_profile


def _route_label(request: Request) -> str:
    route = request.scope.get("route")
    path = getattr(route, "path", None) or "unmatched"
    return f"{request.method} {path}"[:64]


def _save_timing(record: TimingRecord) -> None:
    session = db_session.get_telemetry_sessionmaker()()  # its own pool (ISSUE-013)
    try:
        session.add(record)
        session.commit()
    except Exception:  # noqa: BLE001 - telemetry must never break a request
        session.rollback()
    finally:
        session.close()


def create_app() -> FastAPI:
    settings = get_settings()
    telemetry.configure_logging()
    get_profile()  # a broken Service profile stops the app here
    fernet()  # so does a missing encryption key
    injected = faults.active(settings)  # FAULT_INJECT in production stops the app here
    if injected:
        telemetry.log("faults_injected", faults=sorted(injected))

    app = FastAPI(
        title="rs-assist onboarding", docs_url="/api/docs", openapi_url="/api/openapi.json"
    )

    @app.middleware("http")
    async def timing(request: Request, call_next):
        timings = telemetry.begin()
        try:
            response = await call_next(request)
        except Exception as exc:  # noqa: BLE001
            # The one friendly error boundary: no stack trace or user input in the response
            # or the log line — only the exception type.
            telemetry.log(
                "unhandled_error", endpoint=_route_label(request), error_type=type(exc).__name__
            )
            response = JSONResponse(
                {
                    "detail": "Something went wrong on our side. Your progress is saved — "
                    "please try again in a moment."
                },
                status_code=500,
            )
        if request.url.path.startswith("/api/"):
            label = _route_label(request)
            response.headers["Server-Timing"] = timings.server_timing_header()
            record = TimingRecord(
                endpoint=label,
                status_code=response.status_code,
                total_ms=round(timings.total_ms(), 1),
                llm_ms=_r(timings.stages.get("llm")),
                db_ms=_r(timings.stages.get("db")),
                ocr_ms=_r(timings.stages.get("ocr")),
                outcome=timings.outcome,
                intent=timings.intent,
                provider=timings.provider,
                model=timings.model,
            )
            if label != "GET /api/health":
                await run_in_threadpool(_save_timing, record)
            telemetry.log(
                "request",
                endpoint=label,
                status=response.status_code,
                total_ms=record.total_ms,
                outcome=record.outcome,
            )
        return response

    @app.exception_handler(Unauthenticated)
    async def _unauth(_: Request, exc: Unauthenticated):
        return JSONResponse({"detail": "Please sign in again."}, status_code=401)

    @app.exception_handler(Withdrawn)
    async def _withdrawn(_: Request, exc: Withdrawn):
        return JSONResponse({"detail": "Not found."}, status_code=404)

    @app.exception_handler(Forbidden)
    async def _forbidden(_: Request, exc: Forbidden):
        return JSONResponse({"detail": "You don't have access to that."}, status_code=403)

    @app.exception_handler(RequestValidationError)
    async def _invalid(_: Request, exc: RequestValidationError):
        fields = [".".join(str(p) for p in e.get("loc", [])[1:]) for e in exc.errors()]
        return JSONResponse(
            {"detail": "Some details were not valid.", "fields": fields}, status_code=422
        )

    app.include_router(router)

    dist = Path(settings.frontend_dist).resolve()
    if (dist / "index.html").exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        async def spa(path: str):
            if path.startswith("api/"):
                raise HTTPException(404)
            candidate = dist / path
            if path and candidate.is_file() and dist in candidate.resolve().parents:
                return FileResponse(candidate)
            return FileResponse(dist / "index.html")

    return app


def _r(value: float | None) -> float | None:
    return None if value is None else round(value, 1)


app = create_app()
