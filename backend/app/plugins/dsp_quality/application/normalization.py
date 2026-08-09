from decimal import Decimal, InvalidOperation

from app.plugins.dsp_quality.domain.models import (
    NormalizedQualityValue,
    QualityValueState,
    QualityValueType,
)


NORMALIZATION_RULES = {
    "amazon_scorecard_3.0": {
        "n/a": QualityValueState.NOT_AVAILABLE,
        "not applicable": QualityValueState.NOT_APPLICABLE,
    },
    "quality.v1": {
        "n/a": QualityValueState.NOT_AVAILABLE,
        "not applicable": QualityValueState.NOT_APPLICABLE,
    },
}


def _raw_text(raw_value: object) -> str | None:
    if raw_value is None:
        return None
    return str(raw_value).strip()


def normalize_quality_value(
    raw_value: object,
    value_type: QualityValueType,
    *,
    rating: str | None = None,
    compliance_state: str | None = None,
    rule_version: str = "quality.v1",
) -> NormalizedQualityValue:
    raw = _raw_text(raw_value)
    if raw is None or raw == "":
        return NormalizedQualityValue(
            raw_value=raw,
            value_state=QualityValueState.MISSING,
            rating=rating,
            compliance_state=compliance_state,
            normalization_rule_version=rule_version,
        )
    if raw == "-":
        return NormalizedQualityValue(
            raw_value=raw,
            value_state=QualityValueState.NOT_AVAILABLE,
            rating=rating,
            compliance_state=compliance_state,
            normalization_rule_version=rule_version,
        )
    token_state = NORMALIZATION_RULES.get(
        rule_version,
        NORMALIZATION_RULES["quality.v1"],
    ).get(raw.casefold())
    if token_state is not None:
        return NormalizedQualityValue(
            raw_value=raw,
            value_state=token_state,
            rating=rating,
            compliance_state=compliance_state,
            normalization_rule_version=rule_version,
        )
    if value_type in {
        QualityValueType.CATEGORICAL,
        QualityValueType.COMPLIANCE_STATE,
    }:
        return NormalizedQualityValue(
            raw_value=raw,
            normalized_text_value=raw,
            value_state=QualityValueState.PRESENT,
            rating=rating,
            compliance_state=compliance_state or raw,
            normalization_rule_version=rule_version,
        )

    numeric_token = raw.removesuffix("%").replace(" ", "")
    try:
        numeric = Decimal(numeric_token)
    except InvalidOperation as exc:
        raise ValueError(
            f"Value {raw!r} is not valid for {value_type.value}."
        ) from exc
    if value_type is QualityValueType.COUNT and numeric != numeric.to_integral_value():
        raise ValueError("Count values must be integral.")
    return NormalizedQualityValue(
        raw_value=raw,
        normalized_numeric_value=numeric,
        value_state=QualityValueState.PRESENT,
        rating=rating,
        compliance_state=compliance_state,
        normalization_rule_version=rule_version,
    )
