import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from app.attachments.repository import init_schema as init_attachment_schema
from app.attachments.router import router as attachment_router
from app.auth.middleware import enforce_authentication
from app.auth.organization_router import router as organization_router
from app.auth.repository import init_schema as init_auth_schema
from app.auth.router import router as auth_router
from app.auth.service import bootstrap_user

from app.api.routers import (
    configuration,
    execution_attempt,
    execution_intent,
    health,
    imports,
    legacy_retirement,
    operations,
    planning,
    planning_operations,
    planning_confirmation,
    planning_conflicts,
    planning_drafts,
    planning_publication,
    planning_readiness,
    planning_runtime_output,
    planning_timeline,
    runtime_authority,
    runtime_canary,
    runtime_primary,
    runtime_shadow,
)
from app.briefing.repository import init_schema as init_briefing_schema
from app.briefing.router import router as briefing_router
from app.core.config import FRONTEND_DIR, SETTINGS
from app.core.configuration.repository import (
    init_schema as init_configuration_schema,
)
from app.core.database import claim_legacy_tenant_data, init_db
from app.core.runtime_storage import initialize_runtime_storage
from app.demo.repository import init_schema as init_demo_schema
from app.demo.router import router as demo_router
from app.plugins.dsp_workspace.interfaces.router import router as dsp_workspace_router
from app.plugins.dsp_quality.bootstrap import initialize_dsp_quality_plugin
from app.plugins.fleet.bootstrap import (
    initialize_fleet_plugin,
    register_fleet_plugin,
)
from app.plugins.workforce.bootstrap import (
    initialize_workforce_plugin,
    register_workforce_plugin,
)
from app.repositories.authority_repository import (
    init_schema as init_authority_schema,
)
from app.repositories.execution_intent_repository import (
    init_schema as init_execution_intent_schema,
)
from app.repositories.execution_attempt_repository import (
    init_schema as init_execution_attempt_schema,
)
from app.repositories.planning_draft_repository import (
    init_schema as init_planning_draft_schema,
)
from app.repositories.planning_confirmation_repository import (
    init_schema as init_planning_confirmation_schema,
)
from app.repositories.planning_publication_repository import (
    init_schema as init_planning_publication_schema,
)
from app.workspace.repository import init_schema as init_workspace_schema
from app.workspace.router import router as workspace_router


logging.basicConfig(
    level=getattr(logging, SETTINGS.log_level, logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("operations_engine")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        "Starting Operations Engine environment=%s database=%s",
        SETTINGS.environment,
        SETTINGS.database_backend,
    )
    try:
        initialize_runtime_storage()
        init_db()
        init_auth_schema()
        bootstrap_user()
        claim_legacy_tenant_data()
        init_attachment_schema()
        init_configuration_schema()
        initialize_fleet_plugin()
        initialize_workforce_plugin()
        initialize_dsp_quality_plugin()
        init_briefing_schema()
        init_demo_schema()
        init_workspace_schema()
        init_planning_draft_schema()
        init_planning_confirmation_schema()
        init_planning_publication_schema()
        init_authority_schema()
        init_execution_intent_schema()
        init_execution_attempt_schema()
        yield
    finally:
        logger.info("Operations Engine stopped")


app = FastAPI(
    title="Operations Engine",
    version="1.0.0-rc.1",
    debug=SETTINGS.debug,
    lifespan=lifespan,
)
app.middleware("http")(enforce_authentication)
app.include_router(auth_router)
app.include_router(organization_router)
app.include_router(attachment_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(SETTINGS.cors_origins),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=list(SETTINGS.trusted_hosts),
)


@app.middleware("http")
async def production_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Permissions-Policy"] = (
        "camera=(), geolocation=(), microphone=()"
    )
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "base-uri 'self'; "
        "frame-ancestors 'none'; "
        "img-src 'self' data:; "
        "object-src 'none'; "
        "script-src 'self'; "
        "style-src 'self'; "
        f"connect-src 'self' {SETTINGS.api_origin}"
    )
    if SETTINGS.production:
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )
    if (
        request.url.path in {"/app", "/app/", "/app/sw.js", "/app/manifest.webmanifest"}
        or (request.url.path.startswith("/app/") and request.url.path.endswith(".html"))
    ):
        response.headers["Cache-Control"] = "no-cache"
    elif request.url.path.startswith("/app/assets/"):
        if request.query_params.get("v"):
            response.headers["Cache-Control"] = (
                "public, max-age=31536000, immutable"
            )
        else:
            # Unversioned transitive modules must revalidate on every release.
            response.headers["Cache-Control"] = "no-cache"
    return response


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception(
        "Unhandled request error method=%s path=%s",
        request.method,
        request.url.path,
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Errore interno non previsto. Controlla il backend e riprova."},
    )


@app.get("/", response_model=dict[str, str])
def root() -> RedirectResponse:
    return RedirectResponse(url="/app/", status_code=307)


app.include_router(health.router)
app.include_router(configuration.router)
app.include_router(imports.router)
app.include_router(operations.router)
app.include_router(planning_readiness.router)
app.include_router(planning_conflicts.router)
app.include_router(planning_timeline.router)
app.include_router(planning_drafts.router)
app.include_router(planning_confirmation.router)
app.include_router(planning_publication.router)
app.include_router(runtime_authority.router)
app.include_router(execution_intent.router)
app.include_router(execution_attempt.router)
app.include_router(runtime_shadow.router)
app.include_router(planning_runtime_output.router)
app.include_router(runtime_canary.router)
app.include_router(runtime_primary.router)
app.include_router(legacy_retirement.router)
app.include_router(planning_operations.router)
app.include_router(planning.router)
app.include_router(demo_router)
app.include_router(briefing_router)
app.include_router(workspace_router)
app.include_router(dsp_workspace_router)
register_fleet_plugin(app)
register_workforce_plugin(app)

if FRONTEND_DIR.is_dir():
    app.mount(
        "/app",
        StaticFiles(directory=str(FRONTEND_DIR), html=True),
        name="frontend",
    )
