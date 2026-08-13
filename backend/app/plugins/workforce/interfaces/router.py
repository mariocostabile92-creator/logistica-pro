from pathlib import Path
from urllib.parse import urlparse

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse

from app.auth.domain import Role
from app.auth.permission_service import has_permission

from app.importers.excel_reader import read_validated_upload
from app.importers.workbook_profiler.errors import WorkbookProfileError
from app.plugins.workforce.application import workforce_service
from app.plugins.workforce.application import week_copy_service
from app.plugins.workforce.application import consecutivity_policy, override_service
from app.plugins.workforce.application import driver_shift_planning_service
from app.plugins.workforce.application import legacy_canonical_publication_bridge
from app.plugins.workforce.application import driver_shift_distribution_service
from app.plugins.workforce.application import driver_shift_portal_service
from app.plugins.workforce.application import driver_shift_credentials_service
from app.plugins.workforce.application import driver_shift_driver_session_service
from app.plugins.workforce.application import coverage_service
from app.plugins.workforce.application import legacy_coverage_backfill_service
from app.plugins.workforce.application import day_member_batch_service
from app.plugins.workforce.application.contact_coverage_service import contact_coverage
from app.plugins.workforce.application.consecutivity_service import snapshots as consecutivity_snapshots
from app.plugins.workforce.application.foundation_service import foundation_snapshot
from app.plugins.workforce.domain.errors import (
    WorkforceDayMemberBatchConflictError,
    WorkforceImportError,
    WorkforceMemberNotFoundError,
    WorkforceStatusNotFoundError,
    WorkforceValidationError,
)
from app.plugins.workforce.domain.models import (
    WorkforceDayStatus,
    WorkforceImportPreview,
    WorkforceImportResult,
    WorkforceMember,
    WorkforceFoundationSnapshot,
)
from app.plugins.workforce.domain.day_member_batch import DayMemberBatchResult
from app.plugins.workforce.domain.week_copy import (
    WorkforceWeekCopyConflictError,
    WorkforceWeekCopyPreview,
    WorkforceWeekCopyResult,
)
from app.plugins.workforce.domain.driver_shift_planning import (
    DriverShiftPlanning,
    DriverShiftPlanningError,
    DriverShiftPlanningConflictError,
    DriverShiftPlanningPublication,
    DriverShiftPlanningResolution,
    DriverShiftPlanningResolutionType,
    DriverShiftPlanningMergePreview,
    DriverShiftPlanningList,
    DriverShiftPlanningNotFoundError,
    DriverShiftPlanningSource,
    DriverShiftPlanningSourceNotFoundError,
    MergeClassification,
)
from app.plugins.workforce.domain.legacy_canonical_publication import (
    LegacyCanonicalPublicationPreview,
)
from app.plugins.workforce.domain.driver_shift_distribution import (
    DriverShiftDistributionError,
    DriverShiftDistributionNotFoundError,
    DriverShiftDistributionPeriodError,
    DriverShiftDistributionReadModel,
    DriverShiftPersonalAccessNotFoundError,
    DriverShiftRecipientAccessLink,
    PersonalDriverShiftView,
    DriverShiftPreparedBatch,
)
from app.plugins.workforce.domain.contact_coverage import WorkforceContactCoverage
from app.plugins.workforce.domain.coverage import DailyCoverageResponse
from app.plugins.workforce.domain.legacy_coverage_backfill import (
    LegacyCoverageBackfillPreview,
    LegacyCoverageBackfillResult,
)
from app.plugins.workforce.domain.driver_shift_portal import (
    DriverShiftPortalAccess,
    DriverShiftPortalAvailability,
    DriverShiftPortalInvalidError,
    DriverShiftPortalNotFoundError,
)
from app.plugins.workforce.domain.driver_shift_credentials import (
    DriverShiftCredentialMutationResult,
    DriverShiftCredentialPrepareResult,
    DriverShiftCredentialReadModel,
    DriverShiftCredentialResetResult,
)
from app.plugins.workforce.domain.driver_shift_driver_session import (
    DriverShiftDriverView,
    DriverShiftLoginInvalidError,
    DriverShiftLoginRateLimitedError,
    DriverShiftLogoutView,
    DriverShiftPublicWeek,
    DriverShiftSessionInvalidError,
)
from app.plugins.workforce.infrastructure import read_repository
from app.plugins.workforce.interfaces.schemas import (
    WorkforceCalendarResponse,
    WorkforceChangesResponse,
    WorkforceCoverageResponse,
    WorkforceDayStatusBatchRequest,
    WorkforceDayStatusBatchResponse,
    WorkforceDayMemberBatchRequest,
    WorkforceDayStatusRequest,
    WorkforceWeekCopyRequest,
    WorkforceMembersResponse,
    WorkforceMemberUpdateRequest,
    WorkforceMemberCreateRequest,
    WorkforceStatusResponse,
    ConsecutivityOverrideRequest,
    ConsecutivityPolicyRequest,
    DriverShiftPlanningCreateRequest,
    DriverShiftDistributionPrepareRequest,
    DriverShiftPlanningImportReference,
    DriverShiftPlanningSourceRequest,
    DriverShiftPlanningReplaceSourcesRequest,
    DriverShiftPlanningResolutionRequest,
    DriverShiftPlanningPublishRequest,
    LegacyCanonicalPublishRequest,
    DriverShiftBatchPrepareRequest,
    DriverShiftPortalTokenRequest,
    DriverShiftPortalLoginRequest,
)
from app.core.config import SETTINGS
from app.workspace.status_service import (
    DemoWorkspaceResetRequiredError,
    ensure_real_data_write_allowed,
)


router = APIRouter(
    prefix="/api/plugins/workforce/v1",
    tags=["workforce-plugin-v1"],
)
public_router = APIRouter(tags=["public-driver-shifts"])
DRIVER_SHIFTS_PAGE = Path(__file__).resolve().parents[5] / "frontend" / "driver-shifts" / "index.html"
DRIVER_SHIFTS_ACCESS_PAGE = (
    Path(__file__).resolve().parents[5]
    / "frontend" / "driver-shifts" / "access" / "index.html"
)
PRIVATE_CACHE_HEADERS = {
    "Cache-Control": "no-store, private, max-age=0",
    "Pragma": "no-cache",
}


def _same_origin_public_mutation(request: Request) -> None:
    fetch_site = request.headers.get("sec-fetch-site", "").casefold()
    if fetch_site == "cross-site":
        raise HTTPException(status_code=403, detail="Richiesta non valida.")
    origin = request.headers.get("origin")
    if not origin:
        return
    expected = {
        f"{urlparse(SETTINGS.base_url).scheme}://{urlparse(SETTINGS.base_url).netloc}",
        f"{request.url.scheme}://{request.url.netloc}",
    }
    if origin.rstrip("/") not in expected:
        raise HTTPException(status_code=403, detail="Richiesta non valida.")


def _invalid_driver_session_response() -> PlainTextResponse:
    response = PlainTextResponse(
        "Sessione driver non valida.",
        status_code=401,
        headers=PRIVATE_CACHE_HEADERS,
    )
    response.delete_cookie(
        driver_shift_driver_session_service.SESSION_COOKIE_NAME,
        path=driver_shift_driver_session_service.SESSION_COOKIE_PATH,
        samesite=driver_shift_driver_session_service.SESSION_COOKIE_SAMESITE,
    )
    return response


async def _read_upload(file: UploadFile) -> tuple[bytes, str]:
    content = await read_validated_upload(file)
    return content, file.filename or "workforce-upload"


def _write_error(exc: Exception) -> HTTPException:
    if isinstance(exc, DemoWorkspaceResetRequiredError):
        return HTTPException(
            status_code=409,
            detail={
                "code": "DEMO_WORKSPACE_RESET_REQUIRED",
                "message": str(exc),
            },
        )
    code = getattr(exc, "code", "WORKFORCE_VALIDATION_ERROR")
    return HTTPException(
        status_code=422,
        detail={"code": code, "message": str(exc)},
    )


def _require(request: Request, permission: str):
    user = request.state.user
    if not has_permission(user.role, permission):
        raise HTTPException(status_code=403, detail="Operazione Workforce non autorizzata.")
    return user


def _planning_error(exc: DriverShiftPlanningError | ValueError) -> HTTPException:
    if isinstance(exc, DriverShiftPlanningConflictError):
        return HTTPException(
            status_code=409,
            detail={"code": exc.code, "message": str(exc)},
        )
    if isinstance(
        exc,
        (DriverShiftPlanningNotFoundError, DriverShiftPlanningSourceNotFoundError),
    ):
        return HTTPException(
            status_code=404,
            detail={"code": exc.code, "message": str(exc)},
        )
    return HTTPException(
        status_code=422,
        detail={
            "code": getattr(exc, "code", "DRIVER_SHIFT_PLANNING_INVALID"),
            "message": str(exc),
        },
    )


def _distribution_error(exc: DriverShiftDistributionError) -> HTTPException:
    if isinstance(exc, DriverShiftDistributionNotFoundError):
        status = 404
    elif isinstance(exc, DriverShiftDistributionPeriodError):
        status = 400
    else:
        status = 422
    return HTTPException(
        status_code=status,
        detail={"code": exc.code, "message": str(exc)},
    )


@router.get(
    "/driver-shift-distributions/{distribution_id}/credentials",
    response_model=DriverShiftCredentialReadModel,
)
def get_driver_shift_credentials(
    distribution_id: int, request: Request,
) -> DriverShiftCredentialReadModel:
    try:
        user = _require(request, "workforce:read")
        return driver_shift_credentials_service.credential_status(
            user.organization_id, distribution_id,
        )
    except DriverShiftDistributionError as exc:
        raise _distribution_error(exc) from exc


@router.post(
    "/driver-shift-distributions/{distribution_id}/credentials/prepare",
    response_model=DriverShiftCredentialPrepareResult,
)
def prepare_driver_shift_credentials(
    distribution_id: int, request: Request, response: Response,
) -> DriverShiftCredentialPrepareResult:
    try:
        ensure_real_data_write_allowed()
        user = _require(request, "workforce:write")
        result = driver_shift_credentials_service.prepare_credentials(
            user.organization_id, distribution_id, user.email,
        )
        response.headers.update(PRIVATE_CACHE_HEADERS)
        return result
    except DemoWorkspaceResetRequiredError as exc:
        raise _write_error(exc) from exc
    except DriverShiftDistributionError as exc:
        raise _distribution_error(exc) from exc


@router.post(
    "/credentials/{workforce_member_id}/reset",
    response_model=DriverShiftCredentialResetResult,
)
def reset_driver_shift_credential(
    workforce_member_id: int, request: Request, response: Response,
) -> DriverShiftCredentialResetResult:
    try:
        ensure_real_data_write_allowed()
        user = _require(request, "workforce:write")
        result = driver_shift_credentials_service.reset_credential(
            user.organization_id, workforce_member_id, user.email,
        )
        response.headers.update(PRIVATE_CACHE_HEADERS)
        return result
    except DemoWorkspaceResetRequiredError as exc:
        raise _write_error(exc) from exc
    except DriverShiftDistributionError as exc:
        raise _distribution_error(exc) from exc


@router.post(
    "/credentials/{workforce_member_id}/revoke",
    response_model=DriverShiftCredentialMutationResult,
)
def revoke_driver_shift_credential(
    workforce_member_id: int, request: Request,
) -> DriverShiftCredentialMutationResult:
    try:
        ensure_real_data_write_allowed()
        user = _require(request, "workforce:write")
        return driver_shift_credentials_service.revoke_credential(
            user.organization_id, workforce_member_id, user.email,
        )
    except DemoWorkspaceResetRequiredError as exc:
        raise _write_error(exc) from exc
    except DriverShiftDistributionError as exc:
        raise _distribution_error(exc) from exc


@router.post(
    "/driver-shift-plannings/{planning_id}/distribution",
    response_model=DriverShiftDistributionReadModel,
)
def prepare_driver_shift_distribution(
    planning_id: int,
    request: Request,
    payload: DriverShiftDistributionPrepareRequest | None = None,
) -> DriverShiftDistributionReadModel:
    try:
        ensure_real_data_write_allowed()
        user = _require(request, "workforce:write")
        return driver_shift_distribution_service.prepare_distribution(
            user.organization_id,
            planning_id,
            user.email,
            period_start=payload.period_start if payload else None,
            period_end=payload.period_end if payload else None,
        )
    except DemoWorkspaceResetRequiredError as exc:
        raise _write_error(exc) from exc
    except DriverShiftDistributionError as exc:
        raise _distribution_error(exc) from exc


@router.get(
    "/driver-shift-plannings/{planning_id}/distribution",
    response_model=DriverShiftDistributionReadModel,
)
def get_driver_shift_distribution(
    planning_id: int, request: Request,
) -> DriverShiftDistributionReadModel:
    try:
        user = _require(request, "workforce:read")
        return driver_shift_distribution_service.distribution_for_planning(
            user.organization_id, planning_id,
        )
    except DriverShiftDistributionError as exc:
        raise _distribution_error(exc) from exc


@router.post(
    "/driver-shift-distributions/{distribution_id}/recipients/{recipient_id}/access-link",
    response_model=DriverShiftRecipientAccessLink,
)
def get_driver_shift_recipient_access_link(
    distribution_id: int, recipient_id: int, request: Request,
) -> DriverShiftRecipientAccessLink:
    try:
        user = _require(request, "workforce:write")
        return driver_shift_distribution_service.recipient_access_link(
            user.organization_id, distribution_id, recipient_id,
        )
    except DriverShiftDistributionError as exc:
        raise _distribution_error(exc) from exc


@router.post(
    "/driver-shift-distributions/{distribution_id}/recipients/{recipient_id}/revoke",
    response_model=DriverShiftDistributionReadModel,
)
def revoke_driver_shift_recipient_access(
    distribution_id: int, recipient_id: int, request: Request,
) -> DriverShiftDistributionReadModel:
    try:
        ensure_real_data_write_allowed()
        user = _require(request, "workforce:write")
        return driver_shift_distribution_service.revoke_recipient_access(
            user.organization_id, distribution_id, recipient_id, user.email,
        )
    except DemoWorkspaceResetRequiredError as exc:
        raise _write_error(exc) from exc
    except DriverShiftDistributionError as exc:
        raise _distribution_error(exc) from exc


@router.post(
    "/driver-shift-distributions/{distribution_id}/recipients/{recipient_id}/regenerate",
    response_model=DriverShiftRecipientAccessLink,
)
def regenerate_driver_shift_recipient_access(
    distribution_id: int, recipient_id: int, request: Request,
) -> DriverShiftRecipientAccessLink:
    try:
        ensure_real_data_write_allowed()
        user = _require(request, "workforce:write")
        return driver_shift_distribution_service.regenerate_recipient_access(
            user.organization_id, distribution_id, recipient_id, user.email,
        )
    except DemoWorkspaceResetRequiredError as exc:
        raise _write_error(exc) from exc
    except DriverShiftDistributionError as exc:
        raise _distribution_error(exc) from exc


@router.post(
    "/driver-shift-distributions/{distribution_id}/prepare-batch",
    response_model=DriverShiftPreparedBatch,
)
def prepare_driver_shift_batch(
    distribution_id: int,
    payload: DriverShiftBatchPrepareRequest,
    request: Request,
) -> DriverShiftPreparedBatch:
    try:
        ensure_real_data_write_allowed()
        user = _require(request, "workforce:write")
        return driver_shift_distribution_service.prepare_batch(
            user.organization_id, distribution_id, payload.recipient_ids,
        )
    except DemoWorkspaceResetRequiredError as exc:
        raise _write_error(exc) from exc
    except DriverShiftDistributionError as exc:
        raise _distribution_error(exc) from exc


@router.post(
    "/driver-shift-distributions/{distribution_id}/export.csv",
    response_class=PlainTextResponse,
)
def export_driver_shift_batch(
    distribution_id: int,
    payload: DriverShiftBatchPrepareRequest,
    request: Request,
) -> PlainTextResponse:
    try:
        ensure_real_data_write_allowed()
        user = _require(request, "workforce:write")
        batch = driver_shift_distribution_service.prepare_batch(
            user.organization_id, distribution_id, payload.recipient_ids,
        )
        content = driver_shift_distribution_service.export_batch_csv(batch)
        filename = f"turni-{batch.period_start}_{batch.period_end}.csv"
        return PlainTextResponse(
            content,
            media_type="text/csv; charset=utf-8",
            headers={
                **PRIVATE_CACHE_HEADERS,
                "Content-Disposition": f'attachment; filename="{filename}"',
            },
        )
    except DemoWorkspaceResetRequiredError as exc:
        raise _write_error(exc) from exc
    except DriverShiftDistributionError as exc:
        raise _distribution_error(exc) from exc


@router.get(
    "/driver-shift-distributions/{distribution_id}/portal",
    response_model=DriverShiftPortalAccess,
)
def get_driver_shift_portal(
    distribution_id: int, request: Request,
) -> DriverShiftPortalAccess:
    try:
        user = _require(request, "workforce:read")
        return driver_shift_portal_service.get_portal(
            user.organization_id, distribution_id,
        )
    except DriverShiftDistributionError as exc:
        raise _distribution_error(exc) from exc


@router.post(
    "/driver-shift-distributions/{distribution_id}/portal",
    response_model=DriverShiftPortalAccess,
)
def prepare_driver_shift_portal(
    distribution_id: int, request: Request,
) -> DriverShiftPortalAccess:
    try:
        ensure_real_data_write_allowed()
        user = _require(request, "workforce:write")
        return driver_shift_portal_service.prepare_portal(
            user.organization_id, distribution_id, user.email,
        )
    except DemoWorkspaceResetRequiredError as exc:
        raise _write_error(exc) from exc
    except DriverShiftDistributionError as exc:
        raise _distribution_error(exc) from exc


@router.post(
    "/driver-shift-distributions/{distribution_id}/portal/revoke",
    response_model=DriverShiftPortalAccess,
)
def revoke_driver_shift_portal(
    distribution_id: int, request: Request,
) -> DriverShiftPortalAccess:
    try:
        ensure_real_data_write_allowed()
        user = _require(request, "workforce:write")
        return driver_shift_portal_service.revoke_portal(
            user.organization_id, distribution_id, user.email,
        )
    except DemoWorkspaceResetRequiredError as exc:
        raise _write_error(exc) from exc
    except DriverShiftDistributionError as exc:
        raise _distribution_error(exc) from exc


@router.post(
    "/driver-shift-distributions/{distribution_id}/portal/regenerate",
    response_model=DriverShiftPortalAccess,
)
def regenerate_driver_shift_portal(
    distribution_id: int, request: Request,
) -> DriverShiftPortalAccess:
    try:
        ensure_real_data_write_allowed()
        user = _require(request, "workforce:write")
        return driver_shift_portal_service.regenerate_portal(
            user.organization_id, distribution_id, user.email,
        )
    except DemoWorkspaceResetRequiredError as exc:
        raise _write_error(exc) from exc
    except DriverShiftDistributionError as exc:
        raise _distribution_error(exc) from exc


@public_router.get("/app/driver-shifts", include_in_schema=False)
@public_router.get("/app/driver-shifts/", include_in_schema=False)
def driver_shifts_public_page() -> FileResponse:
    return FileResponse(DRIVER_SHIFTS_PAGE, headers=PRIVATE_CACHE_HEADERS)


@public_router.get("/app/driver-shifts/access", include_in_schema=False)
@public_router.get("/app/driver-shifts/access/", include_in_schema=False)
def driver_shifts_access_page() -> FileResponse:
    return FileResponse(DRIVER_SHIFTS_ACCESS_PAGE, headers=PRIVATE_CACHE_HEADERS)


@public_router.post(
    "/api/public/driver-shifts/access/validate",
    response_model=DriverShiftPortalAvailability,
)
def validate_driver_shift_portal(
    payload: DriverShiftPortalTokenRequest, response: Response,
) -> DriverShiftPortalAvailability:
    response.headers.update(PRIVATE_CACHE_HEADERS)
    try:
        return driver_shift_portal_service.validate_portal(payload.token)
    except (DriverShiftPortalNotFoundError, DriverShiftPortalInvalidError) as exc:
        raise HTTPException(status_code=404, detail="Accesso turni non disponibile.") from exc


@public_router.post(
    "/api/public/driver-shifts/portal/login",
    response_model=DriverShiftDriverView,
)
def login_driver_shift_portal(
    payload: DriverShiftPortalLoginRequest,
    request: Request,
    response: Response,
) -> DriverShiftDriverView:
    response.headers.update(PRIVATE_CACHE_HEADERS)
    _same_origin_public_mutation(request)
    client_ip = request.client.host if request.client else "unknown"
    try:
        view, raw_token, expires_at = driver_shift_driver_session_service.login(
            portal_token=payload.portal_token,
            access_code=payload.access_code,
            pin=payload.pin,
            remember_device=payload.remember_device,
            client_ip=client_ip,
        )
    except DriverShiftLoginRateLimitedError as exc:
        raise HTTPException(
            status_code=429,
            detail="Dati di accesso non validi.",
            headers={"Retry-After": "900", **PRIVATE_CACHE_HEADERS},
        ) from exc
    except DriverShiftLoginInvalidError as exc:
        raise HTTPException(
            status_code=401,
            detail="Dati di accesso non validi.",
            headers=PRIVATE_CACHE_HEADERS,
        ) from exc
    response.set_cookie(
        driver_shift_driver_session_service.SESSION_COOKIE_NAME,
        raw_token,
        **driver_shift_driver_session_service.cookie_options(
            remember_device=payload.remember_device,
            expires_at=expires_at,
        ),
    )
    return view


@public_router.get(
    "/api/public/driver-shifts/me",
    response_model=DriverShiftDriverView,
)
def current_driver_shift_session(
    request: Request,
    response: Response,
):
    response.headers.update(PRIVATE_CACHE_HEADERS)
    raw_token = request.cookies.get(
        driver_shift_driver_session_service.SESSION_COOKIE_NAME
    )
    try:
        return driver_shift_driver_session_service.current_session(raw_token)
    except DriverShiftSessionInvalidError:
        return _invalid_driver_session_response()


@public_router.get(
    "/api/public/driver-shifts/me/shifts",
    response_model=DriverShiftPublicWeek,
)
def current_driver_shift_week(request: Request, response: Response):
    response.headers.update(PRIVATE_CACHE_HEADERS)
    raw_token = request.cookies.get(
        driver_shift_driver_session_service.SESSION_COOKIE_NAME
    )
    try:
        return driver_shift_driver_session_service.current_shifts(raw_token)
    except DriverShiftSessionInvalidError:
        return _invalid_driver_session_response()


@public_router.post(
    "/api/public/driver-shifts/me/acknowledge",
    response_model=DriverShiftPublicWeek,
)
def acknowledge_driver_shift_week(request: Request, response: Response):
    response.headers.update(PRIVATE_CACHE_HEADERS)
    _same_origin_public_mutation(request)
    raw_token = request.cookies.get(
        driver_shift_driver_session_service.SESSION_COOKIE_NAME
    )
    try:
        return driver_shift_driver_session_service.acknowledge_shifts(raw_token)
    except DriverShiftSessionInvalidError:
        return _invalid_driver_session_response()


@public_router.post(
    "/api/public/driver-shifts/logout",
    response_model=DriverShiftLogoutView,
)
def logout_driver_shift_session(
    request: Request,
    response: Response,
) -> DriverShiftLogoutView:
    response.headers.update(PRIVATE_CACHE_HEADERS)
    _same_origin_public_mutation(request)
    driver_shift_driver_session_service.logout(
        request.cookies.get(driver_shift_driver_session_service.SESSION_COOKIE_NAME)
    )
    response.delete_cookie(
        driver_shift_driver_session_service.SESSION_COOKIE_NAME,
        path=driver_shift_driver_session_service.SESSION_COOKIE_PATH,
        samesite=driver_shift_driver_session_service.SESSION_COOKIE_SAMESITE,
    )
    return DriverShiftLogoutView()


@public_router.get(
    "/api/public/driver-shifts/{token}", response_model=PersonalDriverShiftView,
)
def public_driver_shifts(token: str, response: Response) -> PersonalDriverShiftView:
    response.headers.update(PRIVATE_CACHE_HEADERS)
    try:
        return driver_shift_distribution_service.personal_shifts(token)
    except DriverShiftPersonalAccessNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Accesso turni non disponibile.") from exc


@public_router.post(
    "/api/public/driver-shifts/{token}/acknowledge",
    response_model=PersonalDriverShiftView,
)
def acknowledge_public_driver_shifts(
    token: str, response: Response,
) -> PersonalDriverShiftView:
    response.headers.update(PRIVATE_CACHE_HEADERS)
    try:
        return driver_shift_distribution_service.acknowledge(token)
    except DriverShiftPersonalAccessNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Accesso turni non disponibile.") from exc


@router.get(
    "/driver-shift-plannings",
    response_model=DriverShiftPlanningList,
)
def list_driver_shift_plannings(request: Request) -> DriverShiftPlanningList:
    user = _require(request, "workforce:read")
    return driver_shift_planning_service.list_driver_shift_plannings(
        user.organization_id
    )


@router.get(
    "/driver-shift-plannings/current",
    response_model=DriverShiftPlanning | None,
)
def current_driver_shift_planning(
    request: Request,
) -> DriverShiftPlanning | None:
    user = _require(request, "workforce:read")
    return driver_shift_planning_service.current_driver_shift_planning(
        user.organization_id
    )


@router.get(
    "/driver-shift-plannings/import-reference",
    response_model=DriverShiftPlanningImportReference,
)
def resolve_driver_shift_import_reference(
    request: Request,
    fingerprint: str = Query(min_length=1, max_length=128),
) -> DriverShiftPlanningImportReference:
    try:
        user = _require(request, "workforce:read")
        return DriverShiftPlanningImportReference.model_validate(
            driver_shift_planning_service.resolve_import_reference(
                user.organization_id,
                fingerprint,
            )
        )
    except DriverShiftPlanningError as exc:
        raise _planning_error(exc) from exc


@router.put(
    "/driver-shift-plannings/{planning_id}/conflicts/{conflict_key}",
    response_model=DriverShiftPlanningResolution,
)
def resolve_driver_shift_planning_conflict(
    planning_id: int,
    conflict_key: str,
    payload: DriverShiftPlanningResolutionRequest,
    request: Request,
) -> DriverShiftPlanningResolution:
    try:
        ensure_real_data_write_allowed()
        user = _require(request, "workforce:write")
        return driver_shift_planning_service.resolve_conflict(
            user.organization_id, planning_id, conflict_key,
            DriverShiftPlanningResolutionType(payload.resolution_type),
            payload.expected_version,
            selected_source_row_id=payload.selected_source_row_id,
            workforce_member_id=payload.workforce_member_id,
            actor=user.email,
        )
    except DemoWorkspaceResetRequiredError as exc:
        raise _write_error(exc) from exc
    except (DriverShiftPlanningError, ValueError) as exc:
        raise _planning_error(exc) from exc


@router.post(
    "/driver-shift-plannings/{planning_id}/publish",
    response_model=DriverShiftPlanningPublication,
)
def publish_driver_shift_planning(
    planning_id: int,
    payload: DriverShiftPlanningPublishRequest,
    request: Request,
) -> DriverShiftPlanningPublication:
    try:
        ensure_real_data_write_allowed()
        user = _require(request, "workforce:write")
        return driver_shift_planning_service.publish_driver_shift_planning(
            user.organization_id, planning_id, payload.expected_version,
            payload.expected_preview_fingerprint, actor=user.email,
        )
    except DemoWorkspaceResetRequiredError as exc:
        raise _write_error(exc) from exc
    except DriverShiftPlanningError as exc:
        raise _planning_error(exc) from exc


@router.get(
    "/driver-shift-plannings/{planning_id}/legacy-preview",
    response_model=LegacyCanonicalPublicationPreview,
)
def legacy_canonical_publication_preview(
    planning_id: int,
    request: Request,
) -> LegacyCanonicalPublicationPreview:
    try:
        user = _require(request, "workforce:read")
        return legacy_canonical_publication_bridge.preview(
            user.organization_id, planning_id
        )
    except DriverShiftPlanningError as exc:
        raise _planning_error(exc) from exc


@router.post(
    "/driver-shift-plannings/{planning_id}/legacy-publish",
    response_model=DriverShiftPlanningPublication,
)
def legacy_canonical_publication_publish(
    planning_id: int,
    payload: LegacyCanonicalPublishRequest,
    request: Request,
) -> DriverShiftPlanningPublication:
    try:
        ensure_real_data_write_allowed()
        user = _require(request, "workforce:write")
        return legacy_canonical_publication_bridge.publish(
            user.organization_id,
            planning_id,
            payload.expected_version,
            payload.expected_fingerprint,
            actor=user.email,
        )
    except DemoWorkspaceResetRequiredError as exc:
        raise _write_error(exc) from exc
    except DriverShiftPlanningError as exc:
        raise _planning_error(exc) from exc


@router.post(
    "/driver-shift-plannings/{planning_id}/new-revision",
    response_model=DriverShiftPlanning,
    status_code=201,
)
def create_driver_shift_planning_revision(
    planning_id: int,
    request: Request,
) -> DriverShiftPlanning:
    try:
        ensure_real_data_write_allowed()
        user = _require(request, "workforce:write")
        return driver_shift_planning_service.create_new_revision(
            user.organization_id, planning_id, actor=user.email,
        )
    except DemoWorkspaceResetRequiredError as exc:
        raise _write_error(exc) from exc
    except DriverShiftPlanningError as exc:
        raise _planning_error(exc) from exc


@router.get(
    "/driver-shift-plannings/{planning_id}",
    response_model=DriverShiftPlanning,
)
def get_driver_shift_planning(
    planning_id: int,
    request: Request,
) -> DriverShiftPlanning:
    try:
        user = _require(request, "workforce:read")
        return driver_shift_planning_service.get_driver_shift_planning(
            user.organization_id, planning_id
        )
    except DriverShiftPlanningError as exc:
        raise _planning_error(exc) from exc


@router.post(
    "/driver-shift-plannings",
    response_model=DriverShiftPlanning,
    status_code=201,
)
def create_driver_shift_planning(
    payload: DriverShiftPlanningCreateRequest,
    request: Request,
) -> DriverShiftPlanning:
    try:
        ensure_real_data_write_allowed()
        user = _require(request, "workforce:write")
        return driver_shift_planning_service.create_driver_shift_planning(
            user.organization_id,
            payload.period_start,
            payload.period_end,
            payload.label,
            user.email,
        )
    except DemoWorkspaceResetRequiredError as exc:
        raise _write_error(exc) from exc
    except DriverShiftPlanningError as exc:
        raise _planning_error(exc) from exc


@router.post(
    "/driver-shift-plannings/{planning_id}/sources",
    response_model=DriverShiftPlanningSource,
    status_code=201,
)
def add_driver_shift_planning_source(
    planning_id: int,
    payload: DriverShiftPlanningSourceRequest,
    request: Request,
) -> DriverShiftPlanningSource:
    try:
        ensure_real_data_write_allowed()
        user = _require(request, "workforce:write")
        return driver_shift_planning_service.add_source(
            user.organization_id,
            planning_id,
            payload.workforce_import_id,
            actor=user.email,
            source_order=payload.source_order,
        )
    except DemoWorkspaceResetRequiredError as exc:
        raise _write_error(exc) from exc
    except (DriverShiftPlanningError, ValueError) as exc:
        raise _planning_error(exc) from exc


@router.delete(
    "/driver-shift-plannings/{planning_id}/sources/{source_id}",
    status_code=204,
)
def remove_driver_shift_planning_source(
    planning_id: int,
    source_id: int,
    request: Request,
) -> Response:
    try:
        ensure_real_data_write_allowed()
        user = _require(request, "workforce:write")
        driver_shift_planning_service.remove_source(
            user.organization_id, planning_id, source_id
        )
        return Response(status_code=204)
    except DemoWorkspaceResetRequiredError as exc:
        raise _write_error(exc) from exc
    except (DriverShiftPlanningError, ValueError) as exc:
        raise _planning_error(exc) from exc


@router.put(
    "/driver-shift-plannings/{planning_id}/sources",
    response_model=list[DriverShiftPlanningSource],
)
def replace_driver_shift_planning_sources(
    planning_id: int,
    payload: DriverShiftPlanningReplaceSourcesRequest,
    request: Request,
) -> list[DriverShiftPlanningSource]:
    try:
        ensure_real_data_write_allowed()
        user = _require(request, "workforce:write")
        return driver_shift_planning_service.replace_sources(
            user.organization_id,
            planning_id,
            payload.workforce_import_ids,
            actor=user.email,
        )
    except DemoWorkspaceResetRequiredError as exc:
        raise _write_error(exc) from exc
    except (DriverShiftPlanningError, ValueError) as exc:
        raise _planning_error(exc) from exc


@router.get(
    "/driver-shift-plannings/{planning_id}/merge-preview",
    response_model=DriverShiftPlanningMergePreview,
)
def driver_shift_planning_merge_preview(
    planning_id: int,
    request: Request,
    classification: MergeClassification | None = Query(default=None),
    search: str | None = Query(default=None, max_length=160),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> DriverShiftPlanningMergePreview:
    try:
        user = _require(request, "workforce:read")
        return driver_shift_planning_service.merge_preview(
            user.organization_id,
            planning_id,
            classification=classification,
            search=search,
            limit=limit,
            offset=offset,
        )
    except DriverShiftPlanningError as exc:
        raise _planning_error(exc) from exc


@router.get("/status", response_model=WorkforceStatusResponse)
def status(request: Request) -> WorkforceStatusResponse:
    user = _require(request, "workforce:read")
    members = workforce_service.list_members(user.organization_id)
    return WorkforceStatusResponse(
        member_count=len(members),
        latest_import=read_repository.latest_import_summary(),
    )


@router.get("/members", response_model=WorkforceMembersResponse)
def members(request: Request) -> WorkforceMembersResponse:
    user = _require(request, "workforce:read")
    return WorkforceMembersResponse(items=workforce_service.list_members(user.organization_id))


@router.post("/members", response_model=WorkforceMember, status_code=201)
def create_member(payload: WorkforceMemberCreateRequest, request: Request):
    try:
        ensure_real_data_write_allowed()
        user = _require(request, "workforce:write")
        return workforce_service.create_member(
            payload.model_dump(exclude={"actor"}, mode="json"),
            payload.actor or user.email,
            user.organization_id,
        )
    except (DemoWorkspaceResetRequiredError, WorkforceValidationError) as exc:
        raise _write_error(exc) from exc


@router.get("/foundation", response_model=WorkforceFoundationSnapshot)
def foundation(
    request: Request,
    operation_date: str | None = Query(default=None),
) -> WorkforceFoundationSnapshot:
    try:
        user = _require(request, "workforce:read")
        snapshot = foundation_snapshot(operation_date, user.organization_id)
        snapshot.permissions = {
            "can_configure_policy": has_permission(user.role, "workforce:policy:write"),
            "can_override": has_permission(user.role, "workforce:override"),
        }
        return snapshot
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Data operativa non valida.") from exc


@router.get("/consecutivity/policy")
def get_consecutivity_policy(request: Request):
    user = _require(request, "workforce:read")
    return consecutivity_policy.policy(user.organization_id)


@router.put("/consecutivity/policy")
def put_consecutivity_policy(payload: ConsecutivityPolicyRequest, request: Request):
    user = _require(request, "workforce:policy:write")
    try:
        return consecutivity_policy.update_policy(
            user.organization_id, **payload.model_dump(), actor=user.email
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/consecutivity/overrides", status_code=201)
def create_consecutivity_override(payload: ConsecutivityOverrideRequest, request: Request):
    user = _require(request, "workforce:override")
    try:
        return override_service.create_override(
            user.organization_id, **payload.model_dump(), actor=user.email
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/consecutivity/{member_id}")
def member_consecutivity(
    member_id: int,
    request: Request,
    operation_date: str | None = Query(default=None),
):
    user = _require(request, "workforce:read")
    target = operation_date or date.today().isoformat()
    members = [
        item for item in read_repository.list_members(user.organization_id)
        if item.workforce_member_id == member_id
    ]
    if not members:
        raise HTTPException(status_code=404, detail="Driver Workforce non trovato.")
    snapshot = consecutivity_snapshots(user.organization_id, target, members)[member_id]
    return {
        "snapshot": snapshot,
        "override_history": override_service.history(user.organization_id, member_id),
    }


@router.patch("/members/{member_id}", response_model=WorkforceMember)
def update_member(
    member_id: int,
    request: WorkforceMemberUpdateRequest,
    http_request: Request,
):
    try:
        ensure_real_data_write_allowed()
        user = _require(http_request, "workforce:write")
        return workforce_service.update_member(
            member_id,
            request.model_dump(exclude={"actor"}, exclude_unset=True),
            request.actor,
            user.organization_id,
        )
    except (DemoWorkspaceResetRequiredError, WorkforceMemberNotFoundError, WorkforceValidationError) as exc:
        raise _write_error(exc) from exc


@router.get("/calendar", response_model=WorkforceCalendarResponse)
def calendar(
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    member_id: int | None = Query(default=None, gt=0),
) -> WorkforceCalendarResponse:
    return WorkforceCalendarResponse(
        items=workforce_service.list_calendar(date_from, date_to, member_id)
    )


@router.get("/coverage", response_model=WorkforceCoverageResponse)
def coverage(
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
) -> WorkforceCoverageResponse:
    return WorkforceCoverageResponse(
        items=workforce_service.coverage(date_from, date_to)
    )


@router.get("/planning/coverage", response_model=DailyCoverageResponse)
def planning_coverage(
    request: Request,
    date_from: str = Query(...),
    date_to: str = Query(...),
    cycle: str | None = Query(
        default=None, pattern="^(NEXT_DAY|SAME_DAY)$"
    ),
) -> DailyCoverageResponse:
    user = _require(request, "workforce:read")
    try:
        return coverage_service.daily_coverage(
            user.organization_id,
            date_from,
            date_to,
            cycle,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post(
    "/planning/coverage/backfill/preview",
    response_model=LegacyCoverageBackfillPreview,
)
async def preview_legacy_coverage_backfill(
    request: Request,
    file: UploadFile | None = File(default=None),
    workforce_import_id: int | None = Form(default=None, gt=0),
) -> LegacyCoverageBackfillPreview:
    user = _require(request, "workforce:write")
    if user.role != Role.ADMINISTRATOR:
        raise HTTPException(
            status_code=403,
            detail="La preview del backfill legacy richiede un account Amministratore.",
        )
    try:
        content: bytes | None = None
        filename: str | None = None
        if file is not None:
            content, filename = await _read_upload(file)
        return legacy_coverage_backfill_service.preview(
            user.organization_id,
            content=content,
            filename=filename,
            workforce_import_id=workforce_import_id,
        )
    except (
        WorkbookProfileError,
        legacy_coverage_backfill_service.LegacyCoverageBackfillError,
    ) as exc:
        raise _write_error(exc) from exc


@router.post(
    "/planning/coverage/backfill",
    response_model=LegacyCoverageBackfillResult,
)
async def apply_legacy_coverage_backfill(
    request: Request,
    file: UploadFile = File(...),
    workforce_import_id: int = Form(..., gt=0),
    expected_preview_fingerprint: str = Form(
        ..., min_length=64, max_length=64, pattern="^[0-9a-f]{64}$"
    ),
) -> LegacyCoverageBackfillResult:
    user = _require(request, "workforce:write")
    if user.role != Role.ADMINISTRATOR:
        raise HTTPException(
            status_code=403,
            detail="Il backfill legacy richiede un account Amministratore.",
        )
    try:
        ensure_real_data_write_allowed()
        content, filename = await _read_upload(file)
        return legacy_coverage_backfill_service.apply(
            user.organization_id,
            content=content,
            filename=filename,
            workforce_import_id=workforce_import_id,
            expected_preview_fingerprint=expected_preview_fingerprint,
        )
    except legacy_coverage_backfill_service.LegacyCoverageBackfillConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "LEGACY_COVERAGE_PREVIEW_CONFLICT", "message": str(exc)},
        ) from exc
    except (
        DemoWorkspaceResetRequiredError,
        WorkbookProfileError,
        legacy_coverage_backfill_service.LegacyCoverageBackfillError,
    ) as exc:
        raise _write_error(exc) from exc


@router.get("/contact-coverage", response_model=WorkforceContactCoverage)
def workforce_contact_coverage(request: Request) -> WorkforceContactCoverage:
    user = _require(request, "workforce:read")
    return contact_coverage(user.organization_id)


@router.get("/changes", response_model=WorkforceChangesResponse)
def changes(limit: int = Query(default=100, ge=1, le=1000)) -> WorkforceChangesResponse:
    return WorkforceChangesResponse(items=workforce_service.list_changes(limit))


@router.post("/import/preview", response_model=WorkforceImportPreview)
async def import_preview(file: UploadFile = File(...)) -> WorkforceImportPreview:
    try:
        content, filename = await _read_upload(file)
        return workforce_service.preview_import(content, filename)
    except (WorkbookProfileError, WorkforceValidationError) as exc:
        raise _write_error(exc) from exc


@router.post("/import", response_model=WorkforceImportResult)
async def import_confirmed(
    file: UploadFile = File(...),
    confirmed_fingerprint: str = Form(...),
    actor: str = Form("local_operator"),
) -> WorkforceImportResult:
    try:
        ensure_real_data_write_allowed()
        content, filename = await _read_upload(file)
        return workforce_service.apply_import(
            content, filename, confirmed_fingerprint, actor
        )
    except (DemoWorkspaceResetRequiredError, WorkforceImportError, WorkforceValidationError) as exc:
        raise _write_error(exc) from exc


@router.post("/day-status", response_model=WorkforceDayStatus)
def create_day_status(
    request: WorkforceDayStatusRequest,
    http_request: Request,
) -> WorkforceDayStatus:
    try:
        ensure_real_data_write_allowed()
        user = _require(http_request, "workforce:write")
        return workforce_service.save_day_status(
            request.model_dump(exclude={"actor"}, exclude_unset=True), request.actor,
            organization_id=user.organization_id,
        )
    except (DemoWorkspaceResetRequiredError, WorkforceMemberNotFoundError, WorkforceValidationError) as exc:
        raise _write_error(exc) from exc


@router.post("/day-status/batch", response_model=WorkforceDayStatusBatchResponse)
def update_day_statuses_batch(
    request: WorkforceDayStatusBatchRequest,
    http_request: Request,
) -> WorkforceDayStatusBatchResponse:
    try:
        ensure_real_data_write_allowed()
        user = _require(http_request, "workforce:write")
        items = workforce_service.save_day_statuses_batch(
            request.model_dump(exclude={"actor"}, exclude_unset=True),
            request.actor,
            user.organization_id,
        )
        return WorkforceDayStatusBatchResponse(items=items)
    except (
        DemoWorkspaceResetRequiredError,
        WorkforceMemberNotFoundError,
        WorkforceValidationError,
    ) as exc:
        raise _write_error(exc) from exc


@router.post("/day-status/batch-members", response_model=DayMemberBatchResult)
def update_day_statuses_for_members(
    request: WorkforceDayMemberBatchRequest,
    http_request: Request,
) -> DayMemberBatchResult:
    try:
        ensure_real_data_write_allowed()
        user = _require(http_request, "workforce:write")
        return day_member_batch_service.apply(
            request.model_dump(exclude={"actor"}, exclude_unset=True),
            request.actor,
            user.organization_id,
        )
    except WorkforceDayMemberBatchConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": exc.code, "message": str(exc), **exc.details},
        ) from exc
    except (
        DemoWorkspaceResetRequiredError,
        WorkforceMemberNotFoundError,
        WorkforceValidationError,
    ) as exc:
        raise _write_error(exc) from exc


@router.get("/week-copy/preview", response_model=WorkforceWeekCopyPreview)
def preview_week_copy(
    http_request: Request,
    workforce_member_id: int = Query(gt=0),
    target_week_start: str = Query(),
) -> WorkforceWeekCopyPreview:
    try:
        user = _require(http_request, "workforce:write")
        return week_copy_service.preview(
            workforce_member_id,
            target_week_start,
            user.organization_id,
        )
    except (WorkforceMemberNotFoundError, WorkforceValidationError) as exc:
        raise _write_error(exc) from exc


@router.post("/week-copy", response_model=WorkforceWeekCopyResult)
def apply_week_copy(
    request: WorkforceWeekCopyRequest,
    http_request: Request,
) -> WorkforceWeekCopyResult:
    try:
        ensure_real_data_write_allowed()
        user = _require(http_request, "workforce:write")
        return week_copy_service.apply(
            request.workforce_member_id,
            request.target_week_start,
            request.expected_fingerprint,
            request.actor,
            user.organization_id,
        )
    except WorkforceWeekCopyConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    except (
        DemoWorkspaceResetRequiredError,
        WorkforceMemberNotFoundError,
        WorkforceValidationError,
    ) as exc:
        raise _write_error(exc) from exc


@router.patch("/day-status/{status_id}", response_model=WorkforceDayStatus)
def update_day_status(
    status_id: int,
    request: WorkforceDayStatusRequest,
    http_request: Request,
) -> WorkforceDayStatus:
    try:
        ensure_real_data_write_allowed()
        user = _require(http_request, "workforce:write")
        return workforce_service.save_day_status(
            request.model_dump(exclude={"actor"}), request.actor, status_id,
            user.organization_id,
        )
    except (
        DemoWorkspaceResetRequiredError,
        WorkforceMemberNotFoundError,
        WorkforceStatusNotFoundError,
        WorkforceValidationError,
    ) as exc:
        raise _write_error(exc) from exc


@router.get("/contracts/core")
def contracts_core(
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
) -> dict[str, object]:
    return workforce_service.core_contracts(date_from, date_to)


@router.get("/export")
def export(section: str = Query(default="calendar", pattern="^(calendar|coverage|changes)$")) -> Response:
    content = workforce_service.export_csv(section)
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="workforce-{section}.csv"'
        },
    )
