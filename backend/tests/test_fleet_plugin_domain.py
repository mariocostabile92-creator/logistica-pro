import pytest
from pydantic import ValidationError

from app.plugins.fleet.domain.models import (
    AssetEventType,
    availability_event_type,
)
from app.plugins.fleet.interfaces.schemas import (
    AssetCreateRequest,
    AssetDocumentCreateRequest,
)


@pytest.mark.parametrize(
    ("previous", "current", "expected"),
    [
        ("available", "unavailable", AssetEventType.ASSET_UNAVAILABLE),
        ("unavailable", "available", AssetEventType.ASSET_AVAILABLE),
        (
            "available",
            "maintenance",
            AssetEventType.ASSET_MAINTENANCE_STARTED,
        ),
        (
            "maintenance",
            "reserve",
            AssetEventType.ASSET_MAINTENANCE_ENDED,
        ),
        (
            "reserve",
            "reserve",
            AssetEventType.ASSET_AVAILABILITY_OBSERVED,
        ),
        (
            "reserve",
            "inspection_hold",
            AssetEventType.ASSET_AVAILABILITY_CHANGED,
        ),
    ],
)
def test_availability_event_type_is_neutral_and_extensible(
    previous,
    current,
    expected,
):
    assert availability_event_type(previous, current) is expected


def test_capabilities_are_configurable_and_deduplicated():
    request = AssetCreateRequest(
        external_identifier="asset-001",
        capabilities=["electric", "roof_rack_42", "electric"],
        availability="inspection_hold",
    )

    assert request.capabilities == ["electric", "roof_rack_42"]
    assert request.availability == "inspection_hold"


def test_invalid_capability_identifier_is_rejected():
    with pytest.raises(ValidationError):
        AssetCreateRequest(
            external_identifier="asset-001",
            capabilities=["large capacity"],
        )


def test_document_dates_must_be_iso_dates():
    with pytest.raises(ValidationError):
        AssetDocumentCreateRequest(
            document_type="insurance",
            name="Policy",
            expires_on="31/12/2026",
        )
