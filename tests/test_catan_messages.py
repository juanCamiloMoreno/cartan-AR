import json
import random
from unittest.mock import MagicMock

import pytest

from light_map.action_dispatcher import handle_catan_build
from light_map.catan.board import Board, vertex_to_list
from light_map.catan.manager import CatanManager
from light_map.catan.messages import plain_ascii, spanish
from light_map.state.world_state import WorldState


CASES = [
    ("That vertex is not on the board", "Esa esquina no está en el tablero"),
    ("Vertex is already occupied", "Esa esquina ya está ocupada"),
    (
        "Too close to another settlement (the distance rule)",
        "Muy cerca de otra casa (regla de distancia)",
    ),
    (
        "A settlement must be connected to one of your roads",
        "Una casa debe estar conectada a uno de tus caminos",
    ),
    ("A city must replace your own settlement", "Una ciudad debe reemplazar una casa tuya"),
    ("A city must replace the player's own settlement", "Una ciudad debe reemplazar una casa tuya"),
    ("That edge is not on the board", "Ese borde no está en el tablero"),
    ("Edge is already occupied", "Ese borde ya está ocupado"),
    ("Edge is already occupied by another player", "Ese borde ya está ocupado"),
    (
        "A road must connect to your roads or buildings",
        "Un camino debe conectarse con tus caminos o construcciones",
    ),
    (
        "The road must start at the settlement you just placed",
        "El camino debe salir de la casa que acabas de poner",
    ),
    ("No roads left to place", "Ya no te quedan piezas de ese tipo"),
    ("No citys left to place", "Ya no te quedan piezas de ese tipo"),
    ("Not enough cards", "No tienes las cartas necesarias"),
    ("Not allowed now (phase: main)", "No se puede hacer eso ahora (fase: main)"),
    ("It is rojo's turn", "Es el turno de rojo"),
    ("Place a road next", "Ahora toca poner un camino"),
    ("Place a settlement first", "Primero hay que poner una casa"),
    ("azul does not have to roll now", "azul no tiene que tirar el dado ahora"),
    ("A die shows 1 to 6", "Un dado muestra de 1 a 6"),
    ("azul does not have to discard", "azul no tiene que descartar"),
    ("azul must discard exactly 4 cards", "azul debe descartar exactamente 4 cartas"),
    ("Unknown resource", "Recurso desconocido"),
    ("Unknown resource: gold", "Recurso desconocido"),
    ("The robber must move to a different tile", "El ladrón debe moverse a otro hexágono"),
    ("Tile is not on the board", "Ese hexágono no está en el tablero"),
    ("blanco cannot be robbed", "No se puede robar a blanco"),
    ("Choose two different resources", "Elige dos recursos distintos"),
    ("Pieces cannot be removed during a game", "No se pueden quitar piezas durante una partida"),
    ("Between 2 and 4 players are supported", "Se admiten de 2 a 4 jugadores"),
    (
        "rojo still has pieces on the board or cards in hand",
        "rojo todavía tiene piezas en el tablero o cartas en la mano",
    ),
    ("Unknown player: verde", "Jugador desconocido: verde"),
    ("Unknown balance level: perfect", "Nivel de equilibrio desconocido: perfect"),
    ("There is nothing to remove at this vertex", "No hay nada que quitar en esa esquina"),
]


@pytest.mark.parametrize(("english", "expected"), CASES)
def test_every_known_message_has_a_spanish_version(english, expected):
    assert spanish(english) == expected


def test_unknown_messages_pass_through_unchanged():
    assert spanish("Something new") == "Something new"
    assert spanish("") == ""


def test_plain_ascii_drops_accents_for_the_projection():
    assert (
        plain_ascii("El ladrón debe moverse a otro hexágono")
        == "El ladron debe moverse a otro hexagono"
    )
    assert plain_ascii("Elige dos recursos distintos") == "Elige dos recursos distintos"
    assert plain_ascii("¿Quién?").isascii()


def test_the_dashboard_and_the_projection_get_the_spanish_text():
    app = MagicMock()
    manager = CatanManager(board=Board.random(random.Random(1)), rng=random.Random(2))
    manager.load_for_map = lambda _path: True
    app.catan_manager = manager
    state = WorldState()
    manager.new_game(state, 2)
    vertex = next(iter(manager.board.all_vertices()))
    handle_catan_build(
        app,
        {"payload": json.dumps({"player": "azul", "vertex": vertex_to_list(vertex)})},
        state,
    )
    assert state.catan.notice["text"] == "Es el turno de rojo"
    sent = app.notifications.add_notification.call_args.args[0]
    assert sent == "Catan: Es el turno de rojo" and sent.isascii()
