from unittest.mock import MagicMock, patch

import pytest

from light_map.vision.infrastructure.camera import REOPEN_AFTER_FAILED_READS, Camera


@pytest.fixture
def mock_capture():
    """Patches cv2.VideoCapture and returns the mock object."""
    with patch("cv2.VideoCapture") as mock:
        # Configure the mock instance returned by VideoCapture()
        mock_instance = MagicMock()
        mock.return_value = mock_instance
        # Default behavior: camera is open
        mock_instance.isOpened.return_value = True
        yield mock


@pytest.fixture
def mock_is_pi():
    """Patches Camera._is_raspberry_pi and returns the mock."""
    with patch("light_map.vision.infrastructure.camera.Camera._is_raspberry_pi") as mock:
        mock.return_value = False
        yield mock


def test_camera_initialization_standard(mock_capture, mock_is_pi):
    # Setup
    mock_is_pi.return_value = False

    # Test
    cam = Camera(index=1)

    # Verify
    mock_capture.assert_called_with(1)
    # The instance returned by mock_capture() is what cam.cap should be
    assert cam.cap == mock_capture.return_value


def test_camera_read_success(mock_capture):
    # Setup
    mock_instance = mock_capture.return_value
    fake_frame = "image_data"
    mock_instance.read.return_value = (True, fake_frame)

    # Test
    cam = Camera()
    frame = cam.read()

    # Verify
    assert frame == fake_frame
    mock_instance.read.assert_called_once()


def test_camera_context_manager(mock_capture):
    # Setup
    mock_instance = mock_capture.return_value

    # Test
    with Camera():
        pass

    # Verify
    mock_instance.release.assert_called_once()


def test_camera_pi_pipeline_index_0(mock_capture, mock_is_pi):
    import cv2

    mock_is_pi.return_value = True
    cam = Camera(index=0)
    assert cam.cap == mock_capture.return_value
    args, kwargs = mock_capture.call_args
    pipeline = args[0]
    assert "camera-name=/base/axi/pcie@1000120000/rp1/i2c@88000/imx708@1a" in pipeline
    assert args[1] == cv2.CAP_GSTREAMER


def test_camera_pi_pipeline_index_1(mock_capture, mock_is_pi):
    import cv2

    mock_is_pi.return_value = True
    cam = Camera(index=1)
    assert cam.cap is not None
    args, kwargs = mock_capture.call_args
    pipeline = args[0]
    assert "camera-name=/base/axi/pcie@1000120000/rp1/i2c@80000/imx708@1a" in pipeline
    assert args[1] == cv2.CAP_GSTREAMER


def test_camera_pi_pipeline_custom_name(mock_capture, mock_is_pi):
    import cv2

    mock_is_pi.return_value = True
    cam = Camera(camera_name="custom_camera_device_path")
    assert cam.cap is not None
    args, kwargs = mock_capture.call_args
    pipeline = args[0]
    assert "camera-name=custom_camera_device_path" in pipeline
    assert args[1] == cv2.CAP_GSTREAMER


def test_camera_reopens_after_a_dead_stream(mock_capture, mock_is_pi):
    cam = Camera(index=1)
    mock_capture.return_value.read.return_value = (False, None)
    for _ in range(REOPEN_AFTER_FAILED_READS - 1):
        assert cam.read() is None
    assert mock_capture.call_count == 1
    assert cam.read() is None
    assert mock_capture.call_count == 2  # the device was opened again


def test_camera_good_frame_resets_the_failure_count(mock_capture, mock_is_pi):
    cam = Camera(index=1)
    mock_capture.return_value.read.return_value = (False, None)
    for _ in range(REOPEN_AFTER_FAILED_READS - 1):
        cam.read()
    mock_capture.return_value.read.return_value = (True, "frame")
    assert cam.read() == "frame"
    mock_capture.return_value.read.return_value = (False, None)
    for _ in range(REOPEN_AFTER_FAILED_READS - 1):
        cam.read()
    assert mock_capture.call_count == 1


def test_the_mock_camera_does_not_run_faster_than_a_camera():
    import time

    from light_map.vision.infrastructure.camera import MOCK_FRAME_INTERVAL, MagicMockCamera

    mock = MagicMockCamera(8, 8)
    start = time.perf_counter()
    for _ in range(3):
        ok, frame = mock.read()
        assert ok and frame.shape == (8, 8, 3)
    assert time.perf_counter() - start >= 2.5 * MOCK_FRAME_INTERVAL


def test_the_mock_camera_does_not_use_a_huge_frame(monkeypatch):
    monkeypatch.setenv("MOCK_CAMERA", "1")
    cam = Camera(index=0)
    assert (cam.width, cam.height) == (1920, 1080)
    small = Camera(index=0, width=640, height=480)
    assert (small.width, small.height) == (640, 480)
