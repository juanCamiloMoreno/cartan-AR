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
- **Partida con turnos:** además del modo libre (sin reglas) hay una partida con las reglas de
  Catan. Se inicia con "Nueva partida" (2, 3 o 4 jugadores) en el dashboard y sigue estas fases:
  1. **Preparación:** dos rondas de casa + camino; la segunda ronda va en orden inverso y paga una
     carta por cada hexágono vecino de esa casa. Se respeta la regla de distancia y que el camino
     salga de la casa recién puesta.
  2. **Tirar dados:** el jugador en turno tira (o ingresa sus dados reales) y se reparte la producción.
  3. **Un 7:** quienes tengan más de 7 cartas descartan la mitad, el jugador en turno mueve el
     ladrón y roba una carta al azar a uno de los jugadores con construcciones en ese hexágono.
  4. **Turno:** construir pagando (camino 1 madera + 1 arcilla, casa 1 de cada uno salvo mineral,
     ciudad 2 trigo + 3 mineral) con reglas de conexión, comercio con el banco 4:1 y terminar turno.
  5. **Victoria:** el primero en llegar a 10 puntos (casa 1, ciudad 2) gana. Las piezas están
     limitadas (15 caminos, 5 casas, 4 ciudades).
  La proyección muestra arriba qué espera la mesa y resalta el panel del jugador en turno.
- **Generador de tableros:** el panel "Nuevo tablero" del dashboard arma un tablero nuevo con una
  lista de reglas que se activan o desactivan (las cuatro primeras dicen si se *permite* la situación):
  recursos iguales pegados, 6 y 8 pegados (la regla oficial lo prohíbe, por eso viene apagado),
  2 y 12 pegados, números iguales pegados, y barajar los puertos. Además hay tres niveles de
  equilibrio: **al azar**, **más o menos justo** y **muy justo**. Se miden los puntos de probabilidad
  (6 y 8 valen 5, 5 y 9 valen 4, y así hasta 2 y 12 que valen 1) de cada recurso y de cada esquina:
  el nivel justo exige que ningún recurso quede muy por encima de otro y que haya pocas esquinas de
  12 puntos o más. Si las reglas son tan estrictas que no se pueden cumplir, se muestra el mejor
  tablero encontrado y un aviso. También se puede generar desde la línea de comandos:
  `python scripts/generate_catan_board.py --balance fair --no-same-resource`.
- **Puertos:** hay 9 en la costa (4 de 3:1 y 5 de 2:1, uno por recurso) con el reparto del tablero
  oficial (separados por 3 y 4 aristas de costa). Se proyectan y se ven en el dashboard. Quien tenga
  una casa o ciudad en un puerto comercia con el banco a 3:1, o a 2:1 si el puerto es de ese recurso;
  sin puerto sigue siendo 4:1.
- **Armado del tablero por fases:** al marcar "Armar el tablero por fases" antes de elegir el número
  de jugadores, la partida empieza con el tablero **oculto** (solo se ven los hexágonos vacíos y los
  puertos):
  1. **¿Quién empieza?** Cada jugador tira un dado (con la app o con su dado real). El más alto va
     primero; si hay empate, solo los empatados vuelven a tirar.
  2. **Preparación** en ese orden, y de vuelta en orden inverso, sobre el tablero vacío.
  3. **Revelado:** primero aparecen las casillas una por una en orden aleatorio, y luego las fichas de
     número siguiendo una espiral desde afuera hacia el centro. Se puede avanzar paso a paso,
     "Revelar todo", o en modo "Automático" (un paso cada 1.2 segundos). El ladrón aparece junto con
     el desierto.
  4. Al terminar el revelado se pagan las cartas de la segunda casa de cada jugador y empieza el
     turno del primero.
  Mientras tanto el mapa del proyector queda en blanco y se reescribe al terminar el revelado; las
  casillas reveladas se pintan encima. Con "Modo libre" se cancela y el tablero vuelve a verse
  completo.
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

## Probar sin proyector ni cámara

Para jugar solo con el dashboard (por ejemplo para probar las reglas), la ventana de proyección se
puede dejar pequeña y la cámara simulada:

```bash
MOCK_CAMERA=1 LIGHT_MAP_WINDOWED=1 python -m light_map run --maps maps/catan.svg --map maps/catan.svg --no-stereo
```

(en PowerShell: `$env:MOCK_CAMERA=1; $env:LIGHT_MAP_WINDOWED=1` antes del comando). Después abre
`http://localhost:8000`. Cuando una jugada no es válida el dashboard muestra el motivo en rojo
(y también se ve en la proyección).

## Estado y límites

- Probado: dashboard con clics reales, ventana de proyección en el computador, lógica con pruebas
  automáticas y el gesto con manos simuladas.
- **No probado:** con un proyector real sobre una mesa, ni con una mano real para el gesto.
- La calibración usada en las pruebas es falsa; para uso real hay que calibrar cámara y proyector.
- Faltan reglas de Catan: camino más largo, ejército más grande, cartas de desarrollo, comercio
  entre jugadores.
- Los paneles de las esquinas y el gesto de señalar se probaron con imágenes generadas y manos
  simuladas, no con el proyector real.
- Hay pruebas antiguas del repositorio que ya fallaban antes de estos cambios (varias por la
  resolución del reloj de Windows).
