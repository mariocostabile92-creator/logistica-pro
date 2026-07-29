from app.adapters.amazon import AMAZON_ADAPTER
from app.services.normalization_service import suggest_mapping
from app.utils.text_normalizer import normalize_plate, normalize_text


def test_normalize_names():
    assert normalize_text("Disponibilità Mezzo") == "disponibilita mezzo"
    assert normalize_plate(" ab 123 cd ") == "AB123CD"


def test_column_alias_recognition():
    mapping = suggest_mapping(
        ["Nome Driver", "Targa", "Wave"],
        AMAZON_ADAPTER.aliases_for("planning"),
    )
    fields = {item.source_column: item.target_field for item in mapping}
    assert fields["Nome Driver"] == "driver_name"
    assert fields["Targa"] == "vehicle_plate"
    assert fields["Wave"] == "cycle"
