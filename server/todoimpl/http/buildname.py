"""A build's name: a city of over 100,000 people, nearest to Warsaw first (kuhy, 2026-11-20, part 89abc8ca-2).

A short hash is hard to tell apart and to remember; a city name is not. The name comes from the commit count
of HEAD, so every commit on the linear main gets its own: commit 1 is Radom, and once the list runs out the
names start again with a round number (`Radom 2`). The order is by straight-line distance from Warsaw,
rounded; it only has to be stable, so a new city is only ever appended.
"""

from __future__ import annotations

CITIES = (
    "Radom",
    "Płock",
    "Łódź",
    "Kielce",
    "Lublin",
    "Olsztyn",
    "Białystok",
    "Toruń",
    "Włocławek",
    "Brześć",
    "Częstochowa",
    "Bydgoszcz",
    "Elbląg",
    "Tarnów",
    "Rzeszów",
    "Kraków",
    "Grodno",
    "Sosnowiec",
    "Łuck",
    "Katowice",
    "Dąbrowa",
    "Bytom",
    "Królewiec",
    "Tychy",
    "Gdańsk",
    "Zabrze",
    "Gliwice",
    "Opole",
    "Poznań",
    "Gdynia",
    "Lwów",
    "Bielsko",
    "Rybnik",
    "Równe",
    "Baranowicze",
    "Wrocław",
    "Kowno",
    "Ostrawa",
    "Koszalin",
    "Wilno",
    "Mińsk",
    "Tarnopol",
    "Gorzów",
    "Koszyce",
    "Szczecin",
    "Ołomuniec",
    "Brno",
    "Lida",
)


def name(count: int) -> str:
    """Return the name of the build whose HEAD has `count` commits (1 is the first)."""
    index = max(count, 1) - 1
    city = CITIES[index % len(CITIES)]
    lap = index // len(CITIES)
    return city if lap == 0 else f"{city} {lap + 1}"
