import requests
import time


def geocode_address(address: str):
    """
    Trasforma un indirizzo in coordinate lat/lon usando Nominatim OpenStreetMap.
    Versione migliorata:
    - limita ricerca all'Italia
    - gestisce errori JSON
    - rallenta le richieste per evitare blocchi 429
    """

    url = "https://nominatim.openstreetmap.org/search"

    params = {
        "q": address,
        "format": "json",
        "limit": 1,
        "countrycodes": "it"
    }

    headers = {
        "User-Agent": "LogisticaMVP/1.0 demo-locale"
    }

    response = requests.get(url, params=params, headers=headers, timeout=20)

    if response.status_code == 429:
        raise ValueError(
            f"Troppe richieste al servizio gratuito per '{address}'. Aspetta 1 minuto e riprova."
        )

    if response.status_code != 200:
        raise ValueError(
            f"Errore geocoding per '{address}'. Codice: {response.status_code}"
        )

    try:
        data = response.json()
    except Exception:
        raise ValueError(
            f"Risposta non valida dal servizio mappe per: {address}"
        )

    if not data:
        raise ValueError(f"Indirizzo non trovato: {address}")

    time.sleep(1.5)

    return {
        "address": address,
        "lat": float(data[0]["lat"]),
        "lon": float(data[0]["lon"])
    }


def get_distance_km(point_a: dict, point_b: dict):
    """
    Calcola distanza stradale tra due punti usando OSRM pubblico.
    Versione migliorata:
    - gestisce risposte non JSON
    - gestisce limite 429
    - rallenta richieste consecutive
    """

    lon1, lat1 = point_a["lon"], point_a["lat"]
    lon2, lat2 = point_b["lon"], point_b["lat"]

    url = f"https://router.project-osrm.org/route/v1/driving/{lon1},{lat1};{lon2},{lat2}"

    params = {
        "overview": "false",
        "alternatives": "false",
        "steps": "false"
    }

    response = requests.get(url, params=params, timeout=20)

    if response.status_code == 429:
        raise ValueError(
            "Troppe richieste al servizio gratuito OSRM. Aspetta 1 minuto e riprova."
        )

    if response.status_code != 200:
        raise ValueError(
            f"Errore servizio percorso. Codice: {response.status_code}"
        )

    try:
        data = response.json()
    except Exception:
        raise ValueError(
            "Il servizio gratuito OSRM ha risposto male. Riprova tra qualche secondo."
        )

    if "routes" not in data or not data["routes"]:
        raise ValueError("Percorso non trovato tra due tappe.")

    distance_meters = data["routes"][0]["distance"]
    duration_seconds = data["routes"][0]["duration"]

    time.sleep(0.5)

    return {
        "km": round(distance_meters / 1000, 2),
        "minutes": round(duration_seconds / 60)
    }