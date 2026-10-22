"""Hand data for the dashboard debug box: how the camera reads each hand."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from light_map.input.gestures import detect_gesture, is_finger_extended


FINGERS = ("Thumb", "Index", "Middle", "Ring", "Pinky")
LANDMARK_COUNT = 21


def build_hand_debug(hands: list[Any], handedness: list[Any]) -> list[dict[str, Any]]:
    """For each detected hand: its landmarks, handedness, gesture and extended fingers.

    The gesture is classified again from the same landmarks the app uses, so the box shows
    exactly what the app decides. Hands that are malformed are skipped.
    """
    result = []
    for index, raw in enumerate(hands or []):
        try:
            points = [SimpleNamespace(x=float(p["x"]), y=float(p["y"])) for p in raw]
            if len(points) != LANDMARK_COUNT:
                continue
            label = "Left"
            if index < len(handedness or []) and isinstance(handedness[index], dict):
                label = handedness[index].get("label", "Left")
            result.append(
                {
                    "label": label,
                    "gesture": detect_gesture(points, label).name,
                    "fingers": {f: bool(is_finger_extended(points, f, label)) for f in FINGERS},
                    "landmarks": [[round(p.x, 4), round(p.y, 4)] for p in points],
                }
            )
        except (KeyError, TypeError, ValueError):
            continue
    return result
