from app.adapters.amazon import AMAZON_ADAPTER
from app.importers.adapter_contract import TabularImportAdapter


_ACTIVE_TABULAR_IMPORT_ADAPTER: TabularImportAdapter = AMAZON_ADAPTER


def get_active_tabular_import_adapter() -> TabularImportAdapter:
    return _ACTIVE_TABULAR_IMPORT_ADAPTER
