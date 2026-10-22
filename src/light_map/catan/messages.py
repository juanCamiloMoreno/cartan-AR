"""Spanish texts for the moves the rules refuse.

The rules raise English messages; the dashboard and the projection show them in Spanish.
"""

from __future__ import annotations

import re
import unicodedata


# (regex over the English message, Spanish text; groups are available as {1}, {2}...)
_PATTERNS: list[tuple[str, str]] = [
    (r"That vertex is not on the board", "Esa esquina no está en el tablero"),
    (r"Vertex is already occupied", "Esa esquina ya está ocupada"),
    (r"Too close to another settlement.*", "Muy cerca de otra casa (regla de distancia)"),
    (
        r"A settlement must be connected to one of your roads",
        "Una casa debe estar conectada a uno de tus caminos",
    ),
    (
        r"A city must replace (?:your|the player's) own settlement",
        "Una ciudad debe reemplazar una casa tuya",
    ),
    (r"That edge is not on the board", "Ese borde no está en el tablero"),
    (r"Edge is already occupied.*", "Ese borde ya está ocupado"),
    (
        r"A road must connect to your roads or buildings",
        "Un camino debe conectarse con tus caminos o construcciones",
    ),
    (
        r"The road must start at the settlement you just placed",
        "El camino debe salir de la casa que acabas de poner",
    ),
    (r"No (roads|settlements|citys) left to place", "Ya no te quedan piezas de ese tipo"),
    (r"Not enough cards", "No tienes las cartas necesarias"),
    (r"Not allowed now \(phase: (\w+)\)", "No se puede hacer eso ahora (fase: {1})"),
    (r"It is (\w+)'s turn", "Es el turno de {1}"),
    (r"Place a road next", "Ahora toca poner un camino"),
    (r"Place a settlement first", "Primero hay que poner una casa"),
    (r"(\w+) does not have to roll now", "{1} no tiene que tirar el dado ahora"),
    (r"A die shows 1 to 6", "Un dado muestra de 1 a 6"),
    (r"(\w+) does not have to discard", "{1} no tiene que descartar"),
    (r"(\w+) must discard exactly (\d+) cards", "{1} debe descartar exactamente {2} cartas"),
    (r"Unknown resource.*", "Recurso desconocido"),
    (r"The robber must move to a different tile", "El ladrón debe moverse a otro hexágono"),
    (r"Tile is not on the board", "Ese hexágono no está en el tablero"),
    (r"(\w+) cannot be robbed", "No se puede robar a {1}"),
    (r"Choose two different resources", "Elige dos recursos distintos"),
    (r"Pieces cannot be removed during a game", "No se pueden quitar piezas durante una partida"),
    (r"Between 2 and 4 players are supported", "Se admiten de 2 a 4 jugadores"),
    (
        r"(\w+) still has pieces on the board or cards in hand",
        "{1} todavía tiene piezas en el tablero o cartas en la mano",
    ),
    (r"Unknown player: (\w+)", "Jugador desconocido: {1}"),
    (r"Unknown balance level: (\w+)", "Nivel de equilibrio desconocido: {1}"),
    (r"There is nothing to remove at this vertex", "No hay nada que quitar en esa esquina"),
]
_COMPILED = [(re.compile(f"^{pattern}$"), text) for pattern, text in _PATTERNS]


def spanish(message: str) -> str:
    """The Spanish version of a refused-move message, or the message itself if unknown."""
    for pattern, text in _COMPILED:
        match = pattern.match(message)
        if match:
            result = text
            for i, group in enumerate(match.groups(), start=1):
                result = result.replace("{" + str(i) + "}", group)
            return result
    return message


def plain_ascii(text: str) -> str:
    """The text without accents, for the projection whose font cannot draw them."""
    stripped = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return stripped.replace("  ", " ").strip()
