from unittest.mock import MagicMock

import numpy as np
import pytest

from light_map.core.app_context import AppContext
from light_map.core.common_types import (
    AppConfig,
    DetectionResult,
    GestureType,
    ResultType,
)
from light_map.core.scene import HandInput
from light_map.input.input_coordinator import InputCoordinator
from light_map.rendering.layers.cursor_layer import CursorLayer
from light_map.state.world_state import WorldState


@pytest.fixture
def mock_app():
    app = MagicMock()
    config = AppConfig(
        width=1000,
        height=1000,
        projector_matrix=np.eye(3),
    )
    app.config = config
    app.app_context = MagicMock(spec=AppContext)
    app.app_context.last_camera_frame = None
    app.app_context.raw_aruco = {}
    app.app_context.raw_tokens = []
    app.app_context.inspected_token_id = None
    app.inspected_token_id = None

    # Setup input_processor mock
    app.input_processor = MagicMock()
    return app


def test_hand_gesture_timeout_clears_inputs(mock_app):
    """
    Test that when a hand moves away, inputs persist during flicker timeout
    and then expire and are cleared when the timeout expires.
    """
    coordinator = InputCoordinator(mock_app)
    ws = WorldState()

    hand_input = HandInput(
        gesture=GestureType.POINTING,
        proj_pos=(500, 500),
        unit_direction=(1.0, 0.0),
        raw_landmarks=None,
    )
    hand_input.cursor_pos = (550, 500)

    # 1. Hand is detected at t = 10.0
    mock_app.input_processor.convert_mediapipe_to_inputs.return_value = [hand_input]
    res_hand = DetectionResult(
        timestamp=100,
        type=ResultType.HANDS,
        data={"landmarks": [[{"x": 0.5, "y": 0.5, "z": 0.0}]], "handedness": [{"label": "Right"}]},
    )
    ws.apply(res_hand, current_time=10.0)
    coordinator.update(ws, current_time=10.0)

    assert len(ws.inputs) == 1
    assert ws.inputs[0].gesture == GestureType.POINTING
    assert ws.inputs[0].cursor_pos == (550, 500)
    assert ws.last_hand_timestamp == 10.0

    # 2. Hand moves away at t = 10.1. Camera worker sends empty landmarks.
    res_empty = DetectionResult(
        timestamp=101,
        type=ResultType.HANDS,
        data={"landmarks": [], "handedness": []},
    )
    ws.apply(res_empty, current_time=10.1)
    coordinator.update(ws, current_time=10.1)

    # Still within flicker timeout (0.1s <= 0.5s), inputs retained
    assert len(ws.inputs) == 1
    assert ws.inputs[0].gesture == GestureType.POINTING
    assert ws.last_hand_timestamp == 10.0  # Must NOT be overwritten by empty frame

    # 3. Camera keeps producing empty frames at t = 10.3
    ws.apply(res_empty, current_time=10.3)
    coordinator.update(ws, current_time=10.3)
    assert len(ws.inputs) == 1
    assert ws.last_hand_timestamp == 10.0

    # 4. Timeout expires at t = 10.6 (> 0.5s after hand was last seen)
    ws.apply(res_empty, current_time=10.6)
    coordinator.update(ws, current_time=10.6)

    # Inputs and gestures must be cleared!
    assert len(ws.inputs) == 0
    assert ws.gesture is None


def test_cursor_layer_clears_pointer_on_gesture_timeout(mock_app):
    """
    Test that the cursor layer stops rendering the pointer reticle
    after the hand gesture times out.
    """
    coordinator = InputCoordinator(mock_app)
    ws = WorldState()
    layer = CursorLayer(ws, mock_app.app_context)

    hand_input = HandInput(
        gesture=GestureType.POINTING,
        proj_pos=(500, 500),
        unit_direction=(1.0, 0.0),
        raw_landmarks=None,
    )
    hand_input.cursor_pos = (550, 500)

    mock_app.input_processor.convert_mediapipe_to_inputs.return_value = [hand_input]
    res_hand = DetectionResult(
        timestamp=100,
        type=ResultType.HANDS,
        data={"landmarks": [[{"x": 0.5, "y": 0.5, "z": 0.0}]], "handedness": [{"label": "Right"}]},
    )
    ws.apply(res_hand, current_time=1.0)
    coordinator.update(ws, current_time=1.0)

    # Pointer is rendered
    patches, _ = layer.render()
    assert len(patches) == 1

    # Hand moves away, empty frames arrive
    res_empty = DetectionResult(
        timestamp=101,
        type=ResultType.HANDS,
        data={"landmarks": [], "handedness": []},
    )
    ws.apply(res_empty, current_time=1.1)
    coordinator.update(ws, current_time=1.1)

    # Still rendered during flicker period
    patches, _ = layer.render()
    assert len(patches) == 1

    # After timeout expires (> 0.5s)
    ws.apply(res_empty, current_time=1.6)
    coordinator.update(ws, current_time=1.6)

    # Pointer is cleared!
    patches, _ = layer.render()
    assert len(patches) == 0


def test_empty_hand_input_list_does_not_crash(mock_app):
    """
    Test that applying an empty list of HandInputs (e.g. from RemoteDriver)
    clears inputs and does not raise an AttributeError.
    """
    ws = WorldState()
    hand_input = HandInput(
        gesture=GestureType.POINTING,
        proj_pos=(500, 500),
        unit_direction=(1.0, 0.0),
        raw_landmarks=None,
    )
    res_hand = DetectionResult(timestamp=100, type=ResultType.HANDS, data=[hand_input])
    ws.apply(res_hand, current_time=1.0)
    assert len(ws.inputs) == 1

    # Remote driver sends empty list
    res_empty = DetectionResult(timestamp=101, type=ResultType.HANDS, data=[])
    ws.apply(res_empty, current_time=1.1)
    assert len(ws.inputs) == 0
