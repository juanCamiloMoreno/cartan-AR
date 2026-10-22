import pytest

from light_map.input.hand_debug import FINGERS, build_hand_debug
from light_map.state.world_state import WorldState


# Landmark indices (MediaPipe): thumb 1-4, then MCP/PIP/DIP/TIP for each other finger.
FINGER_X = {"Index": 0.42, "Middle": 0.48, "Ring": 0.55, "Pinky": 0.62}
FINGER_BASE = {"Index": 5, "Middle": 9, "Ring": 13, "Pinky": 17}


def make_hand(extended: set[str]) -> list[dict[str, float]]:
    """A synthetic hand in the same format the vision worker sends."""
    points = [{"x": 0.5, "y": 0.9, "z": 0.0} for _ in range(21)]
    for finger, base in FINGER_BASE.items():
        x = FINGER_X[finger]
        up = finger in extended
        points[base] = {"x": x, "y": 0.6, "z": 0.0}  # MCP
        points[base + 1] = {"x": x, "y": 0.5, "z": 0.0}  # PIP
        points[base + 2] = {"x": x, "y": 0.4 if up else 0.55, "z": 0.0}  # DIP
        points[base + 3] = {"x": x, "y": 0.3 if up else 0.62, "z": 0.0}  # TIP
    if "Thumb" in extended:
        points[3] = {"x": 0.32, "y": 0.7, "z": 0.0}
        points[4] = {"x": 0.2, "y": 0.6, "z": 0.0}
    else:
        points[3] = {"x": 0.4, "y": 0.7, "z": 0.0}
        points[4] = {"x": 0.45, "y": 0.65, "z": 0.0}
    return points


@pytest.mark.parametrize(
    ("extended", "gesture"),
    [
        ({"Thumb", "Index", "Middle", "Ring", "Pinky"}, "OPEN_PALM"),
        (set(), "CLOSED_FIST"),
        ({"Index"}, "POINTING"),
        ({"Index", "Middle"}, "VICTORY"),
        ({"Index", "Pinky"}, "ROCK"),
        ({"Thumb", "Index"}, "GUN"),
        ({"Thumb", "Pinky"}, "SHAKA"),
    ],
)
def test_gesture_is_the_one_the_app_classifies(extended, gesture):
    (hand,) = build_hand_debug([make_hand(extended)], [{"label": "Right"}])
    assert hand["gesture"] == gesture


def test_reports_which_fingers_are_extended_and_the_landmarks():
    (hand,) = build_hand_debug([make_hand({"Index", "Pinky"})], [{"label": "Left"}])
    assert hand["label"] == "Left"
    assert hand["fingers"] == {
        "Thumb": False,
        "Index": True,
        "Middle": False,
        "Ring": False,
        "Pinky": True,
    }
    assert set(hand["fingers"]) == set(FINGERS)
    assert len(hand["landmarks"]) == 21
    assert hand["landmarks"][0] == [0.5, 0.9]


def test_two_hands_keep_their_own_label_and_gesture():
    hands = [make_hand(set()), make_hand({"Index", "Middle"})]
    result = build_hand_debug(hands, [{"label": "Left"}, {"label": "Right"}])
    assert [h["label"] for h in result] == ["Left", "Right"]
    assert [h["gesture"] for h in result] == ["CLOSED_FIST", "VICTORY"]


def test_nothing_detected_gives_an_empty_list():
    assert build_hand_debug([], []) == []
    assert build_hand_debug(None, None) == []


def test_malformed_hands_are_skipped_instead_of_breaking_the_state():
    good = make_hand({"Index"})
    result = build_hand_debug([[{"x": 0.1}], good, "nope", [{"y": 1}] * 21], [])
    assert len(result) == 1
    assert result[0]["gesture"] == "POINTING"
    assert result[0]["label"] == "Left"  # no handedness reported


def test_world_state_serializes_the_debug_hands():
    state = WorldState()
    assert state.to_dict()["hand_debug"] == []
    state.hands = [make_hand({"Index", "Pinky"})]
    state.handedness = [{"label": "Right"}]
    (hand,) = state.to_dict()["hand_debug"]
    assert hand["gesture"] == "ROCK"
    assert hand["label"] == "Right"
