"""Known chapter browsing order, with an explicit fallback for other maps."""

import re

CITY_A_ORDER = (
    "1", "2", "3", "4", "3b", "5", "5z", "5a",
    "6", "6z", "6zb", "7zb", "6a", "6b", "s0", "s1", "6c",
    "7", "7z", "8z", "8zb", "8", "7a", "9z", "8b", "9",
    "9b", "9c", "10", "10z", "10zb", "11", "11z", "10a",
    "12", "12z", "12a", "end",
)
CITY_ORDER_SOURCE = "https://berrycamp.github.io/map/celeste/city/a"


def order_rooms(layout: dict, source: str) -> tuple[list[dict], dict]:
    """Order known vanilla rooms by progression, retaining every room exactly once.

    Branches follow the chapter index's browsing convention, not a mandatory
    route through every room. Unknown maps use natural name order, explicitly
    reported as an unverified fallback rather than inferred traversal.
    """
    rooms = layout["rooms"]
    names = [f"lvl_{name}" for name in CITY_A_ORDER]
    if (source == "vanilla" and layout["title"] == "1-ForsakenCity"
            and {room["name"] for room in rooms} == set(names)
            and len(rooms) == len(names)):
        by_name = {room["name"]: room for room in rooms}
        return [by_name[name] for name in names], {
            "basis": "Forsaken City progression index, including side rooms",
            "reference": CITY_ORDER_SOURCE,
        }

    def natural_key(room):
        return [(0, int(part)) if part.isdigit() else (1, part.lower())
                for part in re.split(r"(\d+)", room["name"])]

    return sorted(rooms, key=natural_key), {
        "basis": "Natural room-name order; progression unverified for this map",
    }
