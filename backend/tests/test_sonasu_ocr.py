"""Office RapidOCR gateway (edge.sonasu.jp) mapped into the DocuEngine engine seam."""

from pathlib import Path

import pytest

from app.ocr.sonasu_ocr import (
    SonasuOcrEngine,
    page_result_from_office_payload,
)


def test_maps_office_lines_to_regions_with_axis_aligned_boxes():
    result = page_result_from_office_payload(
        {
            "text": "納品書 No.12345\n株式会社ソナス",
            "lines": [
                {
                    "text": "納品書 No.12345",
                    "score": 0.98603,
                    "box": [[33, 31], [405, 31], [405, 86], [33, 86]],
                },
                {
                    "text": "株式会社ソナス",
                    "score": 0.91,
                    "box": [[40, 100], [300, 100], [300, 140], [40, 140]],
                },
            ],
        }
    )

    assert [r.markdown for r in result.regions] == ["納品書 No.12345", "株式会社ソナス"]
    assert result.regions[0].kind == "text"
    assert result.regions[0].confidence == pytest.approx(0.98603)
    assert result.regions[0].bbox == (33.0, 31.0, 405.0, 86.0)
    assert result.regions[1].bbox == (40.0, 100.0, 300.0, 140.0)


def test_skips_blank_lines_and_falls_back_to_full_text():
    skipped = page_result_from_office_payload(
        {"text": "keep", "lines": [{"text": "  ", "score": 0.9, "box": [[0, 0], [1, 0], [1, 1], [0, 1]]}]}
    )
    assert skipped.regions == []

    fallback = page_result_from_office_payload({"text": "株式会社ソナス\n合計", "lines": []})
    assert len(fallback.regions) == 1
    assert fallback.regions[0].markdown == "株式会社ソナス\n合計"
    assert fallback.regions[0].bbox == (0.0, 0.0, 0.0, 0.0)


def test_parse_page_posts_bearer_json_not_x_api_key(tmp_path, monkeypatch):
    image = tmp_path / "page.png"
    image.write_bytes(b"\x89PNG fake")
    captured: dict = {}

    def fake_post(url, headers, body, timeout):
        captured["url"] = url
        captured["headers"] = headers
        captured["body"] = body
        captured["timeout"] = timeout
        return {
            "text": "見積書",
            "lines": [
                {
                    "text": "見積書",
                    "score": 0.99,
                    "box": [[10, 10], [80, 10], [80, 40], [10, 40]],
                }
            ],
        }

    monkeypatch.setattr(
        "app.config.get_settings",
        lambda: type(
            "S",
            (),
            {
                "sonasu_ocr_base_url": "https://edge.sonasu.jp",
                "sonasu_ocr_api_key": "  sk-test-key\r\n",
                "sonasu_ocr_timeout_seconds": 120,
            },
        )(),
    )
    engine = SonasuOcrEngine(post_json=fake_post)
    engine.load()
    result = engine.parse_page(image)

    assert captured["url"] == "https://edge.sonasu.jp/ocr/ocr"
    assert captured["headers"]["Authorization"] == "Bearer sk-test-key"
    assert "X-Api-Key" not in captured["headers"]
    assert captured["headers"]["Content-Type"] == "application/json"
    assert captured["timeout"] == 120
    assert "image_b64" in captured["body"]
    assert result.regions[0].markdown == "見積書"


def test_load_requires_api_key(monkeypatch):
    monkeypatch.setattr(
        "app.config.get_settings",
        lambda: type(
            "S",
            (),
            {
                "sonasu_ocr_base_url": "https://edge.sonasu.jp",
                "sonasu_ocr_api_key": "  ",
                "sonasu_ocr_timeout_seconds": 120,
            },
        )(),
    )
    engine = SonasuOcrEngine()
    with pytest.raises(RuntimeError, match="SONASU_OCR_API_KEY"):
        engine.load()


def test_http_error_is_actionable_and_does_not_echo_the_key():
    from app.ocr.sonasu_ocr import http_error_message

    message = http_error_message(
        401,
        '{"error":{"message":"Authentication Error"}}',
        api_key="secret-key-value",
    )
    assert "401" in message
    assert "Authentication Error" in message
    assert "secret-key-value" not in message


def test_get_engine_selects_sonasu_ocr(monkeypatch):
    from app.ocr import engine as engine_module

    monkeypatch.setattr(
        "app.config.get_settings",
        lambda: type(
            "S",
            (),
            {
                "ocr_engine": "sonasu-ocr",
                "sonasu_ocr_base_url": "https://edge.sonasu.jp",
                "sonasu_ocr_api_key": "k",
                "sonasu_ocr_timeout_seconds": 120,
                "models_dir": Path("/nonexistent"),
            },
        )(),
    )
    engine_module.reset_engine()
    try:
        engine = engine_module.get_engine()
        assert engine.name == "sonasu-ocr"
    finally:
        engine_module.reset_engine()
