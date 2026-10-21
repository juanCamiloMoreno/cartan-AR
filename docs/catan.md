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
| Acciones | `CATAN_ROLL`, `CATAN_BUILD`, `CATAN_REMOVE`, `CATAN_ROBBER` en `src/light_map/action_dispatcher.py` |
| Dashboard | `frontend/src/components/CatanBoard.tsx`, `CatanPanel.tsx` |
| Gesto | `src/light_map/map/map_scene.py` (`ViewingScene`) |

Se respetó la regla del proyecto: la lectura se hace desde `WorldState` y solo el gestor lo escribe.

## Estado y límites

- Probado: dashboard con clics reales, ventana de proyección en el computador, lógica con pruebas
  automáticas y el gesto con manos simuladas.
- **No probado:** con un proyector real sobre una mesa, ni con una mano real para el gesto.
- La calibración usada en las pruebas es falsa; para uso real hay que calibrar cámara y proyector.
- Faltan reglas de Catan: turnos, cartas, caminos, comercio, puertos, cartas de desarrollo, puntos de
  victoria y descarte con 7.
- Hay pruebas antiguas del repositorio que ya fallaban antes de estos cambios (varias por la
  resolución del reloj de Windows).
