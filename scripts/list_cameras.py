"""Lista las cámaras que entregan imagen y guarda una foto de cada una en la carpeta temporal.

Uso:  python scripts/list_cameras.py
Abre cada foto para saber cuál índice es la cámara USB que mira la mesa.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import cv2


def main() -> None:
    out = Path(tempfile.gettempdir())
    found = False
    for index in range(5):
        cap = cv2.VideoCapture(index)
        frame = None
        if cap.isOpened():
            for _ in range(10):
                ok, frame = cap.read()
        cap.release()
        if frame is None:
            continue
        found = True
        path = out / f"camara_{index}.jpg"
        cv2.imwrite(str(path), frame)
        print(f"Cámara {index}: {frame.shape[1]}x{frame.shape[0]} -> {path}")
    if not found:
        print("No encontré ninguna cámara (¿otro programa la está usando?).")


if __name__ == "__main__":
    main()
