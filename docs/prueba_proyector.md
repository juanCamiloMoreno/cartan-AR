# Prueba con el proyector y la mano

Guía corta. Hacer los pasos en orden; anotar en cuál falla algo.

## Antes de empezar

1. Proyector conectado y Windows en **Extender estas pantallas** (Win+P → Extender).
2. Cámara USB fija, mirando la mesa; **cerrar** la app Cámara, el navegador con cámara, Teams, etc.
3. Luz de la habitación normal (ni muy oscura ni con sol directo sobre la mesa).
4. No mover el proyector ni la cámara desde la calibración. Si se movieron: recalibrar.

## Arrancar

Doble clic en `iniciar_catan.bat` (o `python scripts/iniciar_prueba.py`).
Revisa todo y dice qué falta. Tarda unos 20 s. El panel de control se abre en
<http://localhost:8000>. Para cerrar: Ctrl+C en la ventana negra.

Si no sabes cuál cámara es: `python scripts/list_cameras.py` y mira las fotos; luego
`iniciar_catan.bat 2 1` (cámara 2, pantalla 1).

## Pruebas, en orden

Al arrancar, la proyección abre sola el **modo guiado** (pantallas grandes: jugadores, reglas, dados,
esquinas, qué va primero). Síguelo con las manos: señalar 1 s para botones, puño 3 s en tu esquina,
roca para tirar dado, puño 5 s para pasar turno. Los pasos de abajo son para revisar que cada gesto
funcione.

1. **Encaje:** el tablero proyectado ocupa la mesa y los 4 paneles de jugador se ven en las esquinas.
2. **Mano:** pon la mano abierta sobre la mesa: debe aparecer un aro bajo la mano.
3. **Dados (roca):** cierra el puño 1 s → se tiran los dados.
4. **Partida por fases:** en el dashboard, "Nueva partida" con 3 jugadores y fases. Tira para el orden,
   construye las casas y caminos iniciales (desde el dashboard o el mouse).
5. **Ladrón (señalar):** saca un 7, descarta si toca, y **señala 1 s** el hexágono donde irá el ladrón.
6. **Robar:** señala el panel del jugador al que robas.
7. **Comercio:** ofrece desde el dashboard; quien acepta **señala su propio panel** 1 s.
8. **Panel simple/recursos:** señala un panel vacío 1 s para cambiar el modo.

## Qué contarme

- El número de paso donde algo falló y qué viste (o foto/video).
- Si el aro sigue la mano o va corrido (hacia dónde y cuánto).
- Si algún gesto no se reconoce o se confunde.
- Lo que se lee mal desde lejos (tamaño, color).
