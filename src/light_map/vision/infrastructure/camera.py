import logging
import os
import time

import cv2
import numpy as np


REOPEN_AFTER_FAILED_READS = 60
MOCK_MAX_WIDTH = 1920
MOCK_FRAME_INTERVAL = 1 / 15  # seconds between the frames of the fake camera


class Camera:
    """
    A wrapper around cv2.VideoCapture to handle different camera sources
    (standard webcam vs Raspberry Pi GStreamer).

    CRITICAL NOTE: The default resolution 4608x2592 is INTENTIONAL.
    The camera has a large field of view, and the projected area only covers about
    one quarter of the seen area. High resolution is required for:
    - ArUco marker detection reliability
    - Structured light token detection precision
    - Hand tracking/gesture precision
    DO NOT CHANGE THIS RESOLUTION WITHOUT CONSULTING THE USER.
    """

    def __init__(
        self,
        index: int = 0,
        width: int = 4608,
        height: int = 2592,
        framerate: int = 8,
        camera_name: str | None = None,
    ):
        self.index = index
        self.id = str(index)
        self.width = width
        self.height = height
        self.framerate = framerate
        self.camera_name = camera_name
        self.cap = None
        self._failed_reads = 0
        self._initialize_camera()

    def _is_raspberry_pi(self):
        """Check if the script is running on a Raspberry Pi."""
        try:
            with open("/sys/firmware/devicetree/base/model") as f:
                return "raspberry pi" in f.read().lower()
        except Exception:
            return False

    def _get_gstreamer_pipeline(self):
        """
        Returns a GStreamer pipeline string for capturing from a specific Raspberry Pi camera.
        """
        if self.camera_name is not None and not self.camera_name.startswith("/dev/video"):
            camera_name = self.camera_name
        elif self.index == 1 or self.camera_name == "/dev/video1":
            camera_name = "/base/axi/pcie@1000120000/rp1/i2c@80000/imx708@1a"
        else:
            camera_name = "/base/axi/pcie@1000120000/rp1/i2c@88000/imx708@1a"

        return (
            f"libcamerasrc camera-name={camera_name} af-mode=continuous ! "
            f"video/x-raw, format=BGR, width={self.width}, height={self.height}, framerate={self.framerate}/1 ! "
            f"videoconvert ! "
            f"appsink drop=true sync=false max-buffers=1"
        )

    def _initialize_camera(self):
        if os.environ.get("MOCK_CAMERA") == "1":
            logging.info("MOCK_CAMERA=1 detected. Using dummy camera.")
            if self.width > MOCK_MAX_WIDTH:
                # The default 4608x2592 is a 36 MB frame copied on every frame: far heavier than
                # any real webcam and it slows the whole app down.
                self.width, self.height = 1920, 1080
            self.cap = MagicMockCamera(self.width, self.height)
            return

        if self._is_raspberry_pi():
            logging.info("Raspberry Pi detected. Using GStreamer pipeline.")
            pipeline = self._get_gstreamer_pipeline()
            # logging.debug("Pipeline: %s", pipeline)
            self.cap = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
        else:
            logging.info("Opening standard camera index %d...", self.index)
            self.cap = cv2.VideoCapture(self.index)
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)

            # Read back actual resolution
            self.width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            self.height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            logging.info("Actual camera resolution: %dx%d", self.width, self.height)

        if not self.cap.isOpened():
            raise RuntimeError("Failed to open camera.")

    def read(self):
        """
        Reads a frame from the camera.
        Returns:
            frame: The captured frame, or None if error/end of stream.
        """
        if self.cap is None or not self.cap.isOpened():
            self._reopen()
            return None

        ret, frame = self.cap.read()
        if not ret:
            self._failed_reads += 1
            if self._failed_reads >= REOPEN_AFTER_FAILED_READS:
                self._reopen()
            return None
        self._failed_reads = 0
        return frame

    def _reopen(self):
        """A USB stream that dies mid-run never recovers by itself: open the device again."""
        logging.warning("Camera stopped delivering frames; reopening it.")
        self._failed_reads = 0
        self.release()
        try:
            self._initialize_camera()
        except RuntimeError:
            logging.error("Could not reopen the camera; will retry.")

    def release(self):
        """Releases the camera resource."""
        if self.cap:
            self.cap.release()
            self.cap = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()


class MagicMockCamera:
    """Fake camera for headless environments."""

    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.is_open = True

    def isOpened(self):
        return self.is_open

    def set(self, prop, val):
        return True

    def get(self, prop):
        if prop == cv2.CAP_PROP_FRAME_WIDTH:
            return self.width
        if prop == cv2.CAP_PROP_FRAME_HEIGHT:
            return self.height
        return 0

    def read(self):
        # A black frame at a camera-like pace: an unthrottled fake camera copies frames into
        # shared memory as fast as it can and starves the rest of the app.
        time.sleep(MOCK_FRAME_INTERVAL)
        return True, np.zeros((self.height, self.width, 3), dtype=np.uint8)

    def release(self):
        self.is_open = False
