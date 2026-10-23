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
    (r"The development card deck is empty", "Ya no quedan cartas de desarrollo"),
    (r"That card cannot be played", "Esa carta no se puede jugar"),
    (
        r"Only one development card per turn",
        "Solo se puede jugar una carta de desarrollo por turno",
    ),
    (r"(\w+) does not have that card", "{1} no tiene esa carta"),
    (r"That card was bought this turn", "Esa carta se compró en este turno"),
    (r"Choose two resources", "Elige dos recursos"),
    (r"Choose a resource", "Elige un recurso"),
    (r"There is no open trade offer", "No hay una oferta de comercio abierta"),
    (r"Invalid offer", "La oferta no es válida"),
    (r"A trade offer is already open", "Ya hay una oferta abierta: cancélala primero"),
    (
        r"Offer at least one card and ask for at least one",
        "Ofrece al menos una carta y pide al menos una",
    ),
    (
        r"You cannot trade a resource for the same resource",
        "No se puede cambiar un recurso por el mismo recurso",
    ),
    (r"(\w+) does not have those cards", "{1} no tiene esas cartas"),
    (r"You cannot accept your own offer", "No puedes aceptar tu propia oferta"),
    (r"This offer is for (\w+)", "Esta oferta es para {1}"),
    (r"You cannot trade with yourself", "No puedes comerciar contigo mismo"),
    (r"It is (\w+)'s offer", "La oferta es de {1}"),
    (r"(\w+) already has a corner", "{1} ya tiene esquina"),
    (r"The table has four corners", "La mesa tiene cuatro esquinas"),
    (r"That corner is taken", "Esa esquina ya está ocupada por otro jugador"),
    (r"Choose the map or the houses", "Elige armar el mapa o poner las casas"),
    (r"Choose how many play", "Elige cuántos juegan"),
    (r"That button does nothing now", "Ese botón no hace nada ahora"),
    (r"There is nothing to press now", "No hay nada que pulsar ahora"),
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
