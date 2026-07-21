from app.plugins.fleet.application.registry_configuration import (
    fleet_registry_configuration,
)


BASE_ALIASES = {
    "vehicle_plate": ["targa", "plate", "registration", "mezzo", "furgone"],
    "external_identifier": ["asset id", "id mezzo", "id veicolo", "fleet id"],
    "vehicle_model": ["modello", "model", "tipo mezzo", "veicolo"],
    "category": ["categoria", "category", "classe mezzo"],
    "rental_company": ["societa noleggio", "noleggio", "rental company", "proprietario"],
    "status": ["stato", "status", "condizione"],
    "availability": ["disponibilita", "availability", "operativita"],
    "workshop": ["officina", "garage", "workshop"],
    "damage": ["danno", "guasto", "damage"],
    "replacement_vehicle": ["sostitutivo", "mezzo sostitutivo", "replacement"],
    "parking": ["parcheggio", "parking", "posizione"],
    "fuel_card": ["carta carburante", "fuel card", "shell"],
    "driver_name": ["driver", "autista", "assegnatario"],
    "second_driver_name": ["secondo driver", "secondo autista", "driver 2"],
    "document": ["documento", "document", "assicurazione", "revisione", "bollo"],
    "expirations": ["scadenza", "scadenze", "expiry", "expiration"],
    "tires": ["pneumatici", "gomme", "tires"],
    "equipment": ["dotazioni", "equipment", "accessori"],
    "byod": ["byod", "device"],
    "telepass": ["telepass"],
    "territorial_permit": ["permesso", "permesso territoriale", "ztl"],
    "notes": ["note", "annotazioni", "notes"],
    "delivery_date": ["data consegna", "delivery date"],
    "return_date": ["data restituzione", "return date"],
}


def registry_aliases() -> dict[str, list[str]]:
    aliases = {key: list(values) for key, values in BASE_ALIASES.items()}
    configured = fleet_registry_configuration().get("column_mappings", {})
    if isinstance(configured, dict):
        for field, values in configured.items():
            if field in aliases and isinstance(values, list):
                aliases[field].extend(str(value) for value in values if str(value).strip())
    return aliases
