from router_free import geocode_address, get_distance_km


def optimize_route(depot_address: str, delivery_addresses: list[str]):
    """
    Ottimizzazione semplice:
    parte dal deposito e sceglie ogni volta la consegna più vicina.
    """

    depot = geocode_address(depot_address)

    deliveries = []
    for address in delivery_addresses:
        deliveries.append(geocode_address(address))

    current_point = depot
    remaining = deliveries.copy()
    optimized_route = []

    total_km = 0
    total_minutes = 0

    while remaining:
        best_delivery = None
        best_distance = None

        for delivery in remaining:
            distance_data = get_distance_km(current_point, delivery)

            if best_distance is None or distance_data["km"] < best_distance["km"]:
                best_distance = distance_data
                best_delivery = delivery

        optimized_route.append({
            "address": best_delivery["address"],
            "lat": best_delivery["lat"],
            "lon": best_delivery["lon"],
            "km_from_previous": best_distance["km"],
            "minutes_from_previous": best_distance["minutes"]
        })

        total_km += best_distance["km"]
        total_minutes += best_distance["minutes"]

        current_point = best_delivery
        remaining.remove(best_delivery)

    return {
        "depot": depot,
        "route": optimized_route,
        "total_km": round(total_km, 2),
        "total_minutes": total_minutes
    }