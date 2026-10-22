# Catan en Light Map (experimento)

> **Créditos.** Light Map fue creado por **Rodrigo Chandia**
> ([regelatwork/light-map](https://github.com/regelatwork/light-map)), quien escribió toda la
> plataforma original: calibración, seguimiento de manos, sistema de mapas, dashboard y arquitectura.
> Este documento describe únicamente lo que se agregó encima en este fork experimental.

Este fork es un ejercicio de aprendizaje hecho con ayuda de IA (Claude Code, "vibe coding"). No está
afiliado al autor original ni cuenta con su aprobación. El repositorio original no incluye un archivo
de licencia; esta es una copia personal y sin fines comerciales. Si eres el autor y prefieres que algo
cambie o se retire, abre un issue.

## Qué se agregó

Una capa de juego de Catan que usa la proyección, el dashboard y las manos de Light Map:

- **Tablero:** un generador crea un tablero aleatorio con la distribución oficial (19 hexágonos, 18
  números, sin 6 y 8 adyacentes) como mapa SVG, y guarda el mismo tablero en un archivo `.board.json`
  junto al SVG.
- **Reglas:** tirar los dados, qué hexágonos producen, casas (1 recurso) y ciudades (2), el ladrón
  que bloquea un hexágono, y quiénes pueden ser robados.
- **Proyección:** resalta en dorado los hexágonos que producen, marca al ladrón, dibuja las
  construcciones de cada jugador y muestra los dados con su total.
- **Dashboard:** pestaña "Catan Board" para colocar casas, ciudades, quitarlas y mover al ladrón; panel
  "Tirar dados" (aleatorio o con tus dados reales).
- **Gesto de mano:** mantener **Rock** (índice y meñique) 1 segundo tira los dados, con 4 segundos de
  enfriamiento.
- **Jugadores y estadísticas:** de 2 a 4 jugadores (configurable desde el dashboard). Cada
  jugador tiene mano de cartas, caminos y puntos de victoria (casa = 1, ciudad = 2). Al tirar los
  dados, la producción se suma sola a la mano de cada jugador; en el dashboard se pueden ajustar
  las cartas con + y −.
- **Paneles en las esquinas:** cada jugador tiene un panel en su esquina de la proyección (los de
  arriba se dibujan girados para quien está al otro lado). Tiene dos modos: **simple** (puntos, casas,
  ciudades, caminos y total de cartas) y **recursos** (además, cuántas cartas de cada recurso). Se
  cambia el modo desde el dashboard (por jugador o para todos) o con la mano: mantener el gesto
  **señalar** (solo el índice) 1 segundo sobre el panel de un jugador. Un anillo con el nombre del
  gesto sigue a la mano y se llena mientras la mantienes.
- **Depuración de manos:** el dashboard tiene un recuadro "Depuración de manos" que dibuja el
  esqueleto que detecta la cámara, el nombre del gesto que decide la app (palma, puño, pistola,
  señalar, paz, rock, shaka) y qué dedos ve extendidos. Sirve para ver por qué se confunde un gesto
  con otro. Está en `frontend/src/components/HandDebugPanel.tsx`; los datos salen de
  `src/light_map/input/hand_debug.py` (campo `hand_debug` del estado).
- **Opciones de línea de comandos:** `--camera N` elige la cámara y `--no-stereo` usa una sola.

Se apaga la niebla de guerra automáticamente en los mapas que tienen un tablero de Catan.

## Cómo usarlo

```bash
python scripts/generate_catan_board.py        # crea maps/catan.svg y maps/catan.board.json
light-map run --maps maps/catan.svg --map maps/catan.svg --remote-hands merge --camera 0
```

Después abre `http://localhost:8000` (el dashboard debe estar compilado con `npm run build`).

## Cómo está organizado

```
Gesto / Dashboard ─→ API (/input/action) ─→ ActionDispatcher ─→ CatanManager ─→ WorldState
                                                                      │             ├─→ CatanLayer (proyección)
                                                                      │             └─→ Dashboard (/state/world)
                                                                      └─→ maps/<mapa>.board.json (partida guardada)
```

| Pieza | Archivo |
| :---- | :------ |
| Reglas del tablero | `src/light_map/catan/board.py` |
| Geometría compartida | `src/light_map/catan/layout.py` |
| Gestor (único que escribe el estado) | `src/light_map/catan/manager.py` |
| Capa de proyección | `src/light_map/rendering/layers/catan_layer.py` |
| Acciones | `CATAN_ROLL`, `CATAN_BUILD`, `CATAN_REMOVE`, `CATAN_ROBBER`, `CATAN_ROAD`, `CATAN_CARDS`, `CATAN_PLAYERS`, `CATAN_STATS_MODE` en `src/light_map/action_dispatcher.py` |
| Dashboard | `frontend/src/components/CatanBoard.tsx`, `CatanPanel.tsx`, `CatanStats.tsx` |
| Gesto | `src/light_map/map/map_scene.py` (`ViewingScene`) |

Se respetó la regla del proyecto: la lectura se hace desde `WorldState` y solo el gestor lo escribe.

## Estado y límites

- Probado: dashboard con clics reales, ventana de proyección en el computador, lógica con pruebas
  automáticas y el gesto con manos simuladas.
- **No probado:** con un proyector real sobre una mesa, ni con una mano real para el gesto.
- La calibración usada en las pruebas es falsa; para uso real hay que calibrar cámara y proyector.
- Faltan reglas de Catan: turnos, costos de construcción, camino más largo, comercio, puertos, cartas
  de desarrollo, victoria y descarte con 7. Hoy los caminos y las cartas se llevan sin validar reglas.
- Los paneles de las esquinas y el gesto de señalar se probaron con imágenes generadas y manos
  simuladas, no con el proyector real.
- Hay pruebas antiguas del repositorio que ya fallaban antes de estos cambios (varias por la
  resolución del reloj de Windows).
