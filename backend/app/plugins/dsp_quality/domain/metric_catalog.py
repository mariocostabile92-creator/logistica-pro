from app.plugins.dsp_quality.domain.models import (
    QualityDirection,
    QualityMetricDefinition,
    QualityMetricScope,
    QualityValueType,
)


def _metric(
    key: str,
    label: str,
    category: str,
    value_type: QualityValueType,
    unit: str | None,
    direction: QualityDirection,
    scope: QualityMetricScope,
) -> QualityMetricDefinition:
    return QualityMetricDefinition(
        metric_key=key,
        canonical_label=label,
        category=category,
        value_type=value_type,
        unit=unit,
        direction=direction,
        scope=scope,
    )


METRIC_DEFINITIONS = (
    _metric("overall_score", "Overall Score", "overall", QualityValueType.SCORE, "points", QualityDirection.HIGHER_IS_BETTER, QualityMetricScope.DSP),
    _metric("safe_driving_fico", "Safe Driving Metric (FICO)", "safety", QualityValueType.SCORE, "score_100_850", QualityDirection.HIGHER_IS_BETTER, QualityMetricScope.DSP),
    _metric("speeding_event_rate", "Speeding Event Rate (Per 100 Trips)", "safety", QualityValueType.RATE, "events_per_100_trips", QualityDirection.LOWER_IS_BETTER, QualityMetricScope.DSP),
    _metric("mentor_adoption_rate", "Mentor Adoption Rate", "safety", QualityValueType.PERCENTAGE, "percent", QualityDirection.HIGHER_IS_BETTER, QualityMetricScope.DSP),
    _metric("vsa_compliance", "Vehicle Audit (VSA) Compliance", "compliance", QualityValueType.PERCENTAGE, "percent", QualityDirection.HIGHER_IS_BETTER, QualityMetricScope.DSP),
    _metric("breach_of_contract", "Breach of Contract (BOC)", "compliance", QualityValueType.COMPLIANCE_STATE, "state", QualityDirection.NOT_APPLICABLE, QualityMetricScope.DSP),
    _metric("working_hours_compliance", "Working Hours Compliance (WHC)", "compliance", QualityValueType.PERCENTAGE, "percent", QualityDirection.HIGHER_IS_BETTER, QualityMetricScope.DSP),
    _metric("comprehensive_audit_score", "Comprehensive Audit Score (CAS)", "compliance", QualityValueType.COMPLIANCE_STATE, "state", QualityDirection.NOT_APPLICABLE, QualityMetricScope.DSP),
    _metric("customer_escalation_dpmo", "Customer Escalation DPMO", "customer_delivery_experience", QualityValueType.DPMO, "dpmo", QualityDirection.LOWER_IS_BETTER, QualityMetricScope.DSP),
    _metric("customer_delivery_feedback_dpmo", "Customer Delivery Feedback DPMO", "customer_delivery_experience", QualityValueType.DPMO, "dpmo", QualityDirection.LOWER_IS_BETTER, QualityMetricScope.BOTH),
    _metric("photo_on_delivery", "Photo-On-Delivery", "standard_work_compliance", QualityValueType.PERCENTAGE, "percent", QualityDirection.HIGHER_IS_BETTER, QualityMetricScope.BOTH),
    _metric("contact_compliance", "Contact Compliance", "standard_work_compliance", QualityValueType.PERCENTAGE, "percent", QualityDirection.HIGHER_IS_BETTER, QualityMetricScope.BOTH),
    _metric("delivery_completion_rate", "Delivery Completion Rate (DCR)", "quality", QualityValueType.PERCENTAGE, "percent", QualityDirection.HIGHER_IS_BETTER, QualityMetricScope.BOTH),
    _metric("delivered_not_received_dpmo", "Delivered Not Received (DNR DPMO)", "quality", QualityValueType.DPMO, "dpmo", QualityDirection.LOWER_IS_BETTER, QualityMetricScope.DSP),
    _metric("lost_on_road_dpmo", "Lost on Road (LoR) DPMO", "quality", QualityValueType.DPMO, "dpmo", QualityDirection.LOWER_IS_BETTER, QualityMetricScope.BOTH),
    _metric("delivery_success_conditions_dpmo", "Delivery Success Conditions (DSC DPMO)", "quality", QualityValueType.DPMO, "dpmo", QualityDirection.LOWER_IS_BETTER, QualityMetricScope.BOTH),
    _metric("next_day_capacity_reliability", "Next Day Capacity Reliability", "capacity", QualityValueType.PERCENTAGE, "percent", QualityDirection.HIGHER_IS_BETTER, QualityMetricScope.DSP),
    _metric("same_day_capacity_reliability", "Same Day/Sub-Same Day Capacity Reliability", "capacity", QualityValueType.PERCENTAGE, "percent", QualityDirection.HIGHER_IS_BETTER, QualityMetricScope.DSP),
    _metric("dvic_compliance", "DVIC Compliance", "safety", QualityValueType.PERCENTAGE, "percent", QualityDirection.HIGHER_IS_BETTER, QualityMetricScope.DSP),
    _metric("route_reliability", "Route Reliability", "capacity", QualityValueType.PERCENTAGE, "percent", QualityDirection.HIGHER_IS_BETTER, QualityMetricScope.DSP),
    _metric("delivered", "Delivered", "delivery_quality", QualityValueType.COUNT, "count", QualityDirection.HIGHER_IS_BETTER, QualityMetricScope.TRANSPORTER),
    _metric("customer_escalations_count", "Customer Escalations", "customer_delivery_experience", QualityValueType.COUNT, "count", QualityDirection.LOWER_IS_BETTER, QualityMetricScope.TRANSPORTER),
)


METRIC_DEFINITIONS_BY_KEY = {
    item.metric_key: item for item in METRIC_DEFINITIONS
}
