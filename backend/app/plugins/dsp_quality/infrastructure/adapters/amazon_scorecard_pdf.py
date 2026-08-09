import hashlib
import re
from pathlib import Path

from app.plugins.dsp_quality.application.import_contract import (
    QualityFocusAreaInput,
    QualityIdentityInput,
    QualityMetricInput,
    QualityRevisionInput,
    QualitySectionInput,
    QualitySourceInput,
    QualityStandardRuleInput,
    QualityStandardsInput,
    QualityTransporterInput,
    QualityWorkingHourExceptionInput,
    QualityWorkingHoursInput,
)
from app.plugins.dsp_quality.domain.metric_catalog import METRIC_DEFINITIONS_BY_KEY
from app.plugins.dsp_quality.infrastructure.adapters.pdf_text import read_pdf_text


TEMPLATE_VERSION = "amazon_scorecard_pdf_3_x"
VALUE_PATTERN = r"(N/A|Not Applicable|None|In Compliance|-|\d+(?:\.\d+)?%?)"
RATING_PATTERN = r"(Fantastic|Great|Fair|Poor)"


class AmazonScorecardPdfAdapter:
    adapter_id = "amazon.scorecard.pdf"
    parser_version = "q3.pdf.1"

    _metric_specs = (
        ("safe_driving_fico", r"Safe Driving Metric \(FICO\)"),
        ("speeding_event_rate", r"Speeding Event Rate \(Per 100 Trips\)"),
        ("mentor_adoption_rate", r"Mentor Adoption Rate"),
        ("vsa_compliance", r"Vehicle Audit \(VSA\) Compliance"),
        ("breach_of_contract", r"Breach of Contract \(BOC\)"),
        ("working_hours_compliance", r"Working Hours Compliance \(WHC\)"),
        ("comprehensive_audit_score", r"Comprehensive Audit Score \(CAS\)"),
        ("customer_escalation_dpmo", r"Customer escalation DPMO"),
        ("customer_delivery_feedback_dpmo", r"Customer Delivery Feedback"),
        ("photo_on_delivery", r"Photo-On-Delivery"),
        ("contact_compliance", r"Contact Compliance"),
        ("delivery_completion_rate", r"Delivery Completion Rate\s*\(DCR\)"),
        ("delivered_not_received_dpmo", r"Delivered Not Received\s*\(DNR DPMO\)"),
        ("lost_on_road_dpmo", r"Lost on Road \(LoR\) DPMO"),
        (
            "delivery_success_conditions_dpmo",
            r"Delivery Success Conditions \(DSC DPMO\)",
        ),
        ("next_day_capacity_reliability", r"Next Day Capacity Reliability"),
        (
            "same_day_capacity_reliability",
            r"Same Day/Sub-Same Day Capacity Reliability",
        ),
    )

    _section_specs = (
        ("compliance_and_safety", "Compliance and Safety"),
        ("delivery_quality_and_swc", "Delivery Quality & SWC"),
        ("capacity", "Capacity"),
    )

    _focus_metric_keys = {
        "Delivery Success Conditions (DSC) DPMO": "delivery_success_conditions_dpmo",
        "Delivery Completion Rate (DCR)": "delivery_completion_rate",
        "CDF DPMO": "customer_delivery_feedback_dpmo",
    }

    _standard_specs = {
        "Scorecard Performance": "overall_score",
        "Vehicle Audit Compliance (VSA)": "vsa_compliance",
        "Safe Driving (FICO)": "safe_driving_fico",
        "DVIC Compliance": "dvic_compliance",
        "Speeding Event Rate (per 100 trips)": "speeding_event_rate",
        "Customer Escalation DPMO": "customer_escalation_dpmo",
        "Customer Delivery Feedback DPMO": "customer_delivery_feedback_dpmo",
        "Route Reliability": "route_reliability",
        "Delivery Completion Rate (DCR)": "delivery_completion_rate",
        "Delivery Success Conditions (DSC DPMO)": "delivery_success_conditions_dpmo",
        "Photo On Delivery": "photo_on_delivery",
        "Contact Compliance": "contact_compliance",
        "Lost on Road DPMO": "lost_on_road_dpmo",
    }

    def supports(self, source: QualitySourceInput) -> bool:
        if Path(source.filename).suffix.casefold() != ".pdf":
            return False
        if source.media_type and source.media_type.casefold() != "application/pdf":
            return False
        if not source.content.startswith(b"%PDF"):
            return False
        try:
            return self.detect_template(source) is not None
        except ValueError:
            return False

    def detect_template(self, source: QualitySourceInput) -> str | None:
        document = read_pdf_text(source.content)
        signals = (
            "DSP WEEKLY SCORECARD" in document.text,
            "DSP WEEKLY SUMMARY" in document.text,
            "Performance Standards and Service Levels" in document.text,
            "Transporter ID Delivered DCR DSC DPMO" in document.text,
        )
        return TEMPLATE_VERSION if all(signals) else None

    def geography_is_inferred(self, source: QualitySourceInput) -> bool:
        return self._geography(source) is not None

    def extract_identity(self, source: QualitySourceInput) -> QualityIdentityInput:
        page = self._page(source, 2)
        provider = re.search(r"(?m)^([A-Z0-9]+) at ([A-Z0-9]+)$", page)
        period = re.search(r"(?m)^Week\s+(\d{1,2})\s*-\s*(\d{4})$", page)
        if not provider:
            raise ValueError("DSP identifier or station is missing.")
        if not period:
            raise ValueError("Reported week or year is missing.")
        return QualityIdentityInput(
            dsp_identifier=provider.group(1),
            station=provider.group(2),
            reported_week=int(period.group(1)),
            reported_year=int(period.group(2)),
            geography=self._geography(source),
        )

    def extract_revision(self, source: QualitySourceInput) -> QualityRevisionInput:
        page = self._page(source, 2)
        identity = self.extract_identity(source)
        rank = re.search(
            rf"Rank at {re.escape(identity.station)}:\s*(\d+)\s*\(\s*([+-]?\d+)\s+WoW\)",
            page,
        )
        overall = re.search(
            r"Overall Score:\s*(\d+(?:\.\d+)?)\s*\|\s*([A-Za-z ]+)",
            page,
        )
        period = re.search(r"(?m)^(Week\s+\d{1,2}\s*-\s*\d{4})$", page)
        return QualityRevisionInput(
            source_filename=Path(source.filename).name,
            parser_adapter=self.adapter_id,
            parser_version=self.parser_version,
            detected_template_version=self.detect_template(source),
            rank=int(rank.group(1)) if rank else None,
            rank_wow_declared=int(rank.group(2)) if rank else None,
            overall_score=overall.group(1) if overall else None,
            overall_standing=overall.group(2).strip() if overall else None,
            raw_period_label=period.group(1) if period else None,
            normalization_rule_version="amazon_scorecard_3.0",
        )

    def extract_dsp_metrics(self, source: QualitySourceInput) -> list[QualityMetricInput]:
        page = self._page(source, 2)
        revision = self.extract_revision(source)
        metrics = []
        if revision.overall_score is not None:
            metrics.append(
                QualityMetricInput(
                    metric_key="overall_score",
                    raw_value=revision.overall_score,
                    rating=revision.overall_standing,
                    source_page=2,
                    source_table="DSP WEEKLY SCORECARD",
                    extracted_label="Overall Score",
                )
            )
        for metric_key, label_pattern in self._metric_specs:
            match = re.search(
                rf"{label_pattern}\s+{VALUE_PATTERN}(?:\|{RATING_PATTERN})?",
                page,
                re.IGNORECASE,
            )
            if not match:
                continue
            raw_value = match.group(1)
            rating = match.group(2) if match.lastindex and match.lastindex >= 2 else None
            metrics.append(
                QualityMetricInput(
                    metric_key=metric_key,
                    raw_value=raw_value,
                    rating=rating,
                    compliance_state=(
                        raw_value
                        if metric_key in {"breach_of_contract", "comprehensive_audit_score"}
                        else None
                    ),
                    source_page=2,
                    source_table="DSP WEEKLY SCORECARD",
                    extracted_label=METRIC_DEFINITIONS_BY_KEY[metric_key].canonical_label,
                )
            )
        return metrics

    def extract_section_standings(self, source: QualitySourceInput) -> list[QualitySectionInput]:
        page = self._page(source, 2)
        result = []
        for key, label in self._section_specs:
            match = re.search(
                rf"(?m)^{re.escape(label)}\s*:?[ \t]+(Fantastic|Great|Fair|Poor)$",
                page,
                re.IGNORECASE,
            )
            if match:
                result.append(
                    QualitySectionInput(
                        section_key=key,
                        section_label=label,
                        standing=match.group(1).title(),
                        source_page=2,
                    )
                )
        return result

    def extract_transporter_rows(self, source: QualitySourceInput) -> list[QualityTransporterInput]:
        metric_keys = (
            "delivered",
            "delivery_completion_rate",
            "delivery_success_conditions_dpmo",
            "lost_on_road_dpmo",
            "photo_on_delivery",
            "contact_compliance",
            "customer_escalations_count",
            "customer_delivery_feedback_dpmo",
        )
        result = []
        for page_number in (3, 4, 5):
            for line in self._page(source, page_number).splitlines():
                tokens = line.split()
                if len(tokens) != 9 or not re.fullmatch(r"[A-Z0-9]{8,20}", tokens[0]):
                    continue
                metrics = [
                    QualityMetricInput(
                        metric_key=key,
                        raw_value=value,
                        source_page=page_number,
                        source_table="DSP WEEKLY SUMMARY",
                        source_row=tokens[0],
                        source_column=key,
                        extracted_label=METRIC_DEFINITIONS_BY_KEY[key].canonical_label,
                    )
                    for key, value in zip(metric_keys, tokens[1:], strict=True)
                ]
                result.append(
                    QualityTransporterInput(
                        transporter_external_id=tokens[0],
                        row_index=len(result) + 1,
                        source_page=page_number,
                        raw_row_fingerprint=hashlib.sha256(
                            line.encode("utf-8")
                        ).hexdigest(),
                        metrics=metrics,
                    )
                )
        return result

    def extract_working_hour_exceptions(self, source: QualitySourceInput) -> QualityWorkingHoursInput:
        page = self._page(source, 6)
        present = "Drivers With Working Hour Exceptions" in page
        exceptions = []
        for line in page.splitlines():
            match = re.fullmatch(
                r"\s*\d+\s+([A-Z0-9]{8,20})\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s*",
                line,
            )
            if not match:
                continue
            exceptions.append(
                QualityWorkingHourExceptionInput(
                    transporter_external_id=match.group(1),
                    daily_limit_exceeded=match.group(2),
                    weekly_limit_exceeded=match.group(3),
                    under_offwork_limit=match.group(4),
                    work_day_limit_exceeded=match.group(5),
                    wh_exception=match.group(6),
                    source_page=6,
                    source_row=line.strip(),
                )
            )
        return QualityWorkingHoursInput(section_present=present, exceptions=exceptions)

    def extract_focus_areas(self, source: QualitySourceInput) -> list[QualityFocusAreaInput]:
        page = self._page(source, 2)
        result = []
        for match in re.finditer(r"(?m)^(\d+)\.\s+(.+?)\s*$", page):
            label = match.group(2).strip()
            if label not in self._focus_metric_keys:
                continue
            result.append(
                QualityFocusAreaInput(
                    position=int(match.group(1)),
                    metric_key=self._focus_metric_keys[label],
                    source_label=label,
                    source_page=2,
                )
            )
        return result

    def extract_standard_rules(self, source: QualitySourceInput) -> QualityStandardsInput | None:
        page = self._page(source, 7)
        if "Performance Standards and Service Levels" not in page:
            return None
        rules = []
        for source_label, metric_key in self._standard_specs.items():
            match = re.search(
                rf"(?m)^{re.escape(source_label)}\s+(\S+)\s+(\S+)\s*$",
                page,
                re.IGNORECASE,
            )
            if not match:
                continue
            definition = METRIC_DEFINITIONS_BY_KEY[metric_key]
            rules.append(
                QualityStandardRuleInput(
                    metric_key=metric_key,
                    target_value=match.group(1),
                    minimum_value=match.group(2),
                    unit=definition.unit,
                    direction=definition.direction,
                    raw_target=match.group(1),
                    raw_minimum=match.group(2),
                    source_page=7,
                )
            )
        identity = self.extract_identity(source)
        return QualityStandardsInput(
            geography_scope=identity.geography,
            station_scope=identity.station,
            detected_source_version=TEMPLATE_VERSION,
            rules=rules,
        )

    @staticmethod
    def _geography(source: QualitySourceInput) -> str | None:
        prefix = Path(source.filename).name.split("-", 1)[0].upper()
        return prefix if re.fullmatch(r"[A-Z]{2}", prefix) else None

    @staticmethod
    def _page(source: QualitySourceInput, page_number: int) -> str:
        document = read_pdf_text(source.content)
        if len(document.pages) < page_number:
            return ""
        return document.pages[page_number - 1]
