from __future__ import annotations

import numpy as np
import pytest

from digital_pen.camera.esp32_client import Esp32CameraClient, parse_pgm


def test_parse_pgm_returns_original_grayscale_pixels() -> None:
    pixels = bytes(range(8))

    image = parse_pgm(b"P5\n4 2\n255\n" + pixels)

    assert image.shape == (2, 4)
    assert image.dtype == np.uint8
    np.testing.assert_array_equal(image, np.arange(8, dtype=np.uint8).reshape(2, 4))


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (b"P2\n1 1\n255\n0", "P5"),
        (b"P5\n1 1\n256\n\x00", "8-bit"),
        (b"P5\n2 1\n255\n\x00", "pixel data"),
        (b"P5\n1 1\n255\n\x00\x01", "pixel data"),
    ],
)
def test_parse_pgm_rejects_invalid_payload(payload: bytes, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        parse_pgm(payload)


class _FakeResponse:
    def __init__(
        self,
        *,
        content: bytes = b"",
        headers: dict[str, str] | None = None,
        json_body: dict[str, object] | None = None,
    ) -> None:
        self.content = content
        self.headers = headers or {}
        self._json_body = json_body or {}

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return self._json_body


class _FakeSession:
    def __init__(self, responses: list[_FakeResponse]) -> None:
        self._responses = iter(responses)
        self.requests: list[tuple[str, float]] = []

    def get(self, url: str, *, timeout: float) -> _FakeResponse:
        self.requests.append((url, timeout))
        return next(self._responses)


def test_client_builds_camera_frame_from_headers_and_pgm() -> None:
    response = _FakeResponse(
        content=b"P5\n4 2\n255\n" + bytes(range(8)),
        headers={
            "X-Frame-Id": "42",
            "X-Timestamp-Us": "123456",
            "X-Exposure": "321",
        },
    )
    session = _FakeSession([response])
    client = Esp32CameraClient(
        "http://192.168.4.1/", timeout_s=3.5, session=session
    )

    frame = client.capture()

    assert frame.frame_id == 42
    assert frame.timestamp_us == 123456
    assert frame.exposure == 321
    assert frame.image.shape == (2, 4)
    assert session.requests == [("http://192.168.4.1/capture.pgm", 3.5)]


def test_client_status_returns_json_object() -> None:
    session = _FakeSession([_FakeResponse(json_body={"sensor": "OV5640"})])
    client = Esp32CameraClient("http://camera.local", session=session)

    status = client.status()

    assert status == {"sensor": "OV5640"}
