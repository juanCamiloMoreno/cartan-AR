import pytest

from light_map.core import display_utils
from light_map.core.display_utils import (
    SCREEN_ENV,
    get_screen_resolution,
    screen_rect,
    selected_screen,
)


MONITORS = [(0, 0, 1920, 1080), (1920, 0, 1371, 771)]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    monkeypatch.delenv(SCREEN_ENV, raising=False)


@pytest.fixture
def two_monitors(monkeypatch):
    monkeypatch.setattr(display_utils, "list_monitors", lambda: MONITORS)


def test_no_screen_selected_by_default():
    assert selected_screen() is None
    assert screen_rect() is None


@pytest.mark.parametrize(
    ("raw", "expected"), [("1", 1), ("0", 0), ("-3", 0), ("x", None), ("", None)]
)
def test_selected_screen_parses_the_environment(monkeypatch, raw, expected):
    monkeypatch.setenv(SCREEN_ENV, raw)
    assert selected_screen() == expected


def test_screen_rect_returns_the_chosen_monitor(monkeypatch, two_monitors):
    monkeypatch.setenv(SCREEN_ENV, "1")
    assert screen_rect() == (1920, 0, 1371, 771)
    assert screen_rect(0) == (0, 0, 1920, 1080)


def test_unknown_screen_falls_back_to_the_last_monitor(monkeypatch, two_monitors):
    monkeypatch.setenv(SCREEN_ENV, "7")
    assert screen_rect() == (1920, 0, 1371, 771)


def test_without_monitor_info_the_default_behaviour_is_kept(monkeypatch):
    monkeypatch.setattr(display_utils, "list_monitors", lambda: [])
    monkeypatch.setenv(SCREEN_ENV, "1")
    assert screen_rect() is None


def test_resolution_is_the_one_of_the_chosen_monitor(monkeypatch, two_monitors):
    monkeypatch.setenv(SCREEN_ENV, "1")
    assert get_screen_resolution() == (1371, 771)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(None, 0.7), ("0.4", 0.4), ("abc", 0.7), ("5", 1.0), ("0", 0.1)],
)
def test_hand_detection_confidence_is_adjustable_and_clamped(monkeypatch, raw, expected):
    from light_map.vision.infrastructure.workers import (
        HAND_CONFIDENCE_ENV,
        hand_detection_confidence,
    )

    if raw is None:
        monkeypatch.delenv(HAND_CONFIDENCE_ENV, raising=False)
    else:
        monkeypatch.setenv(HAND_CONFIDENCE_ENV, raw)
    assert hand_detection_confidence() == expected
