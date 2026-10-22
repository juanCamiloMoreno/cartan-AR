import numpy as np

from light_map.core.common_types import GestureType
from light_map.core.constants import (
    INDEX_MCP,
    INDEX_PIP,
    INDEX_TIP,
    MIDDLE_PIP,
    MIDDLE_TIP,
    PINKY_MCP,
    PINKY_PIP,
    PINKY_TIP,
    RING_PIP,
    RING_TIP,
    THUMB_IP,
    THUMB_TIP,
    WRIST,
)


# A finger counts as straight when the angle at its PIP joint (MCP - PIP - tip) is at least this.
# The distance-from-wrist check alone calls a finger "extended" when it is curled toward the
# camera, which a low camera over the table sees all the time.
STRAIGHT_FINGER_MIN_ANGLE = 140.0
# Landmarks are normalized to the image, so x and z must be stretched to the 16:9 frame
# before angles mean anything.
FRAME_ASPECT = 16 / 9
_FINGER_MCP = {"Index": 5, "Middle": 9, "Ring": 13, "Pinky": 17}


def _pip_angle(landmarks, mcp_idx, pip_idx, tip_idx) -> float:
    """Angle in degrees at the PIP joint between the proximal and distal bones."""

    def point(i):
        p = landmarks[i]
        return np.array([p.x * FRAME_ASPECT, p.y, getattr(p, "z", 0.0) * FRAME_ASPECT], dtype=float)

    v1 = point(mcp_idx) - point(pip_idx)
    v2 = point(tip_idx) - point(pip_idx)
    norm = np.linalg.norm(v1) * np.linalg.norm(v2)
    if norm == 0:
        # No bone to measure (missing landmarks): do not veto the distance check.
        return 180.0
    return float(np.degrees(np.arccos(np.clip(np.dot(v1, v2) / norm, -1.0, 1.0))))


def is_finger_extended(landmarks, finger_name, hand_label="Right"):
    """
    Determines if a finger is extended based on landmark positions.
    Using a simplified distance-from-wrist heuristic which is robust for 2D.
    """
    # 0 is Wrist
    wrist = landmarks[WRIST]

    if finger_name == "Thumb":
        tip = landmarks[THUMB_TIP]
        ip = landmarks[THUMB_IP]

        # Thumb is extended if the tip is further from the index finger MCP (5)
        # than the IP joint is? Or simple distance from wrist?
        # Thumb is tricky because it moves sideways.
        # Let's check if Tip is far from the Palm center (approx landmark 9 or 5/17 avg)

        # Thumb is extended if the tip is further from the pinky MCP than the IP joint
        # AND it must be far enough from the index MCP to be considered "spread out"
        pinky_mcp = landmarks[PINKY_MCP]
        index_mcp = landmarks[INDEX_MCP]

        d_tip_pinky = np.linalg.norm(
            np.array([tip.x, tip.y]) - np.array([pinky_mcp.x, pinky_mcp.y])
        )
        d_ip_pinky = np.linalg.norm(np.array([ip.x, ip.y]) - np.array([pinky_mcp.x, pinky_mcp.y]))

        d_tip_index = np.linalg.norm(
            np.array([tip.x, tip.y]) - np.array([index_mcp.x, index_mcp.y])
        )
        palm_width = np.linalg.norm(
            np.array([index_mcp.x, index_mcp.y]) - np.array([pinky_mcp.x, pinky_mcp.y])
        )

        return (d_tip_pinky > d_ip_pinky) and (d_tip_index > palm_width * 0.4)

    else:
        # For other fingers, we check if the tip is further from the wrist than the PIP joint.
        # This works well for "Open" vs "Fist"

        indices = {
            "Index": (INDEX_TIP, INDEX_PIP),  # Tip, PIP
            "Middle": (MIDDLE_TIP, MIDDLE_PIP),
            "Ring": (RING_TIP, RING_PIP),
            "Pinky": (PINKY_TIP, PINKY_PIP),
        }

        tip_idx, pip_idx = indices[finger_name]
        tip = landmarks[tip_idx]
        pip = landmarks[pip_idx]

        # Calculate distance to wrist (0)
        d_tip = np.linalg.norm(np.array([tip.x, tip.y]) - np.array([wrist.x, wrist.y]))
        d_pip = np.linalg.norm(np.array([pip.x, pip.y]) - np.array([wrist.x, wrist.y]))

        straight = _pip_angle(landmarks, _FINGER_MCP[finger_name], pip_idx, tip_idx) >= (
            STRAIGHT_FINGER_MIN_ANGLE
        )
        return bool(d_tip > d_pip) and straight


def detect_gesture(landmarks, handedness_label):
    """
    Classifies the hand gesture based on landmarks.

    Args:
        landmarks: List of normalized landmark objects (from MediaPipe).
        handedness_label: "Left" or "Right".

    Returns:
        GestureType: detected gesture.
    """
    fingers = ["Thumb", "Index", "Middle", "Ring", "Pinky"]
    state = {f: is_finger_extended(landmarks, f, handedness_label) for f in fingers}

    # Logic
    # All open -> Open Palm
    if all(state.values()):
        return GestureType.OPEN_PALM

    # All closed -> Closed Fist
    if not any(state.values()):
        return GestureType.CLOSED_FIST

    # Thumb + Index -> Gun
    if (
        state["Thumb"]
        and state["Index"]
        and not state["Middle"]
        and not state["Ring"]
        and not state["Pinky"]
    ):
        return GestureType.GUN

    # Index only -> Pointing
    if state["Index"] and not state["Middle"] and not state["Ring"] and not state["Pinky"]:
        # Thumb state can vary for pointing (sometimes tucked, sometimes out)
        # Let's allow thumb to be anything or strict?
        # "Pointing" usually implies thumb is tucked or neutral.
        return GestureType.POINTING

    # Index + Middle -> Victory
    if state["Index"] and state["Middle"] and not state["Ring"] and not state["Pinky"]:
        return GestureType.VICTORY

    # Index + Pinky -> Rock? (Optional)
    if state["Index"] and state["Pinky"] and not state["Middle"] and not state["Ring"]:
        return GestureType.ROCK

    # Thumb + Pinky -> Shaka / Phone
    if (
        state["Thumb"]
        and state["Pinky"]
        and not state["Index"]
        and not state["Middle"]
        and not state["Ring"]
    ):
        return GestureType.SHAKA

    return GestureType.UNKNOWN
