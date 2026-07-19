import json
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel

from app.importers.adapter_contract import (
    AdapterConceptMapping,
    AdapterEventMapping,
)


CATALOG_PATH = Path(__file__).with_name("catalog.v1.json")


class AmazonAdapterCatalog(BaseModel):
    adapter_id: str
    contract_version: str
    datasets: dict[str, dict[str, list[str]]]
    recognized_operational_units: list[str]
    concept_mappings: list[AdapterConceptMapping]
    event_mappings: list[AdapterEventMapping]


@lru_cache(maxsize=1)
def load_catalog() -> AmazonAdapterCatalog:
    payload = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    return AmazonAdapterCatalog.model_validate(payload)
