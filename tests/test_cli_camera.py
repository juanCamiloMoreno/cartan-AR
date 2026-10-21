import pytest

from light_map.__main__ import build_parser


def parse(*argv: str):
    parser, _ = build_parser()
    return parser.parse_args(["run", *argv])


def test_camera_defaults_to_the_first_device():
    assert parse().camera == 0


def test_camera_can_be_selected():
    assert parse("--camera", "1").camera == 1


def test_stereo_stays_on_by_default():
    assert parse().no_stereo is False


def test_no_stereo_turns_the_second_camera_off():
    assert parse("--no-stereo").no_stereo is True


def test_camera_rejects_negative_indexes():
    with pytest.raises(SystemExit):
        parse("--camera", "-1")


def test_camera_rejects_non_numbers():
    with pytest.raises(SystemExit):
        parse("--camera", "usb")
