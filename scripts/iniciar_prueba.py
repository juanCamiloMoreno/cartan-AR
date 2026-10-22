"""Arranca la app de Catan para la prueba con el proyector, revisando antes que todo esté listo.

Uso:  python scripts/iniciar_prueba.py [--camera 1] [--screen 1] [--confidence 0.4]
                                       [--map maps/catan.svg] [--windowed]

Revisa: pantallas conectadas, calibración guardada, mapa y dashboard compilado, y que la cámara
entregue imagen. Si falta algo importante, lo dice con una frase clara; si no se ve el
proyector, abre la proyección en una ventana pequeña para no tapar la pantalla principal.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

CALIBRATION_FILES = (
    ("projector_calibration.npz", "calibración del proyector"),
    ("camera_calibration.npz", "datos de la cámara"),
    ("camera_extrinsics.npz", "posición de la cámara"),
)


def build_launch(
    camera: int,
    screen: int,
    confidence: float,
    map_path: str,
    monitors: list,
    windowed: bool = False,
    mock_camera: bool = False,
) -> tuple[list[str], dict[str, str], list[str]]:
    """El comando, el entorno extra y los avisos para arrancar la app."""
    warnings: list[str] = []
    env: dict[str, str] = {}
    if screen >= len(monitors) and not windowed:
        warnings.append(
            f"No veo la pantalla {screen} (hay {len(monitors)} conectada(s)): "
            "¿está el proyector conectado como pantalla extendida? "
            "La proyección se abrirá en una ventana pequeña."
        )
        windowed = True
    if windowed:
        env["LIGHT_MAP_WINDOWED"] = "1"
    if mock_camera:
        env["MOCK_CAMERA"] = "1"
    command = [
        sys.executable,
        "-m",
        "light_map",
        "run",
        "--maps",
        map_path,
        "--map",
        map_path,
        "--remote-hands",
        "merge",
        "--camera",
        str(camera),
        "--screen",
        str(screen),
        "--no-stereo",
        "--hand-confidence",
        str(confidence),
    ]
    return command, env, warnings


def missing_files(data_dir: Path, map_path: Path, dist: Path) -> list[str]:
    """Qué falta para que la prueba funcione (lista vacía si todo está)."""
    problems = []
    for name, meaning in CALIBRATION_FILES:
        if not (data_dir / name).exists():
            problems.append(f"Falta la {meaning} ({name}): hay que calibrar (calibrar.bat).")
    if not map_path.exists() or not map_path.with_name(map_path.stem + ".board.json").exists():
        problems.append(
            "Falta el tablero (mapa y .board.json): corre "
            "python scripts/generate_catan_board.py --balance fair"
        )
    if not (dist / "index.html").exists():
        problems.append("El dashboard no está compilado: en la carpeta frontend corre npm run build.")
    return problems


def camera_report(index: int) -> str | None:
    """None si la cámara entrega imagen; si no, una frase explicando qué pasa."""
    import cv2

    cap = cv2.VideoCapture(index)
    try:
        if not cap.isOpened():
            return f"No se pudo abrir la cámara {index}."
        frame = None
        for _ in range(15):
            ok, frame = cap.read()
        if frame is None:
            return (
                f"La cámara {index} abre pero no entrega imagen "
                "(¿otro programa la está usando, como la app Cámara o el navegador?)."
            )
        if float(frame.mean()) < 15:
            return f"La cámara {index} entrega una imagen casi negra: ¿es la cámara correcta?"
        return None
    finally:
        cap.release()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--camera", type=int, default=1, help="índice de la cámara USB (1)")
    parser.add_argument("--screen", type=int, default=1, help="pantalla del proyector (1)")
    parser.add_argument("--confidence", type=float, default=0.4, help="umbral de detección de manos")
    parser.add_argument("--map", default="maps/catan.svg")
    parser.add_argument("--windowed", action="store_true", help="proyección en ventana pequeña")
    parser.add_argument("--skip-camera-check", action="store_true")
    parser.add_argument("--mock-camera", action="store_true", help="sin cámara real (pruebas)")
    args = parser.parse_args()

    from light_map.core.display_utils import list_monitors
    from light_map.core.storage import StorageManager

    os.chdir(ROOT)
    monitors = list_monitors()
    print(f"Pantallas: {[(m[2], m[3]) for m in monitors]}")

    data_dir = Path(StorageManager().get_data_dir())
    problems = missing_files(data_dir, Path(args.map), ROOT / "frontend" / "dist")
    for problem in problems:
        print("✗", problem)
    if problems:
        print("\nArréglalo y vuelve a intentar.")
        return 1

    if not (args.skip_camera_check or args.mock_camera):
        print(f"Probando la cámara {args.camera}...")
        issue = camera_report(args.camera)
        if issue:
            print("✗", issue)
            return 1
        print("✓ La cámara entrega imagen.")

    command, env, warnings = build_launch(
        args.camera, args.screen, args.confidence, args.map, monitors, args.windowed, args.mock_camera
    )
    for warning in warnings:
        print("!", warning)
    print("\nArrancando (la cámara tarda unos 20 segundos en abrirse)...")
    print("Dashboard: http://localhost:8000     Para cerrar: Ctrl+C en esta ventana\n")
    try:
        return subprocess.call(command, env={**os.environ, **env}, cwd=ROOT)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
