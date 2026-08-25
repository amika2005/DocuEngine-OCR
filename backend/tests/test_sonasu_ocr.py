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


def _line(text, x0, y0, x1, y1, score=0.95):
    return {
        "text": text,
        "score": score,
        "box": [[x0, y0], [x1, y0], [x1, y1], [x0, y1]],
    }


def test_office_payload_assembles_item_grid_into_markdown_table():
    result = page_result_from_office_payload(
        {
            "text": "納品書\n品目\n単価\n数量\n価格\nマスター管理\n45,000\n38\n1,710,000",
            "lines": [
                _line("納品書", 40, 30, 140, 70),
                _line("品目", 40, 400, 120, 430),
                _line("単価", 200, 400, 270, 430),
                _line("数量", 320, 400, 390, 430),
                _line("価格", 460, 400, 540, 430),
                _line("マスター管理", 40, 450, 180, 480),
                _line("45,000", 200, 450, 270, 480),
                _line("38", 320, 450, 360, 480),
                _line("1,710,000", 460, 450, 560, 480),
            ],
        }
    )
    tables = [r for r in result.regions if r.kind == "table"]
    assert len(tables) == 1
    md = tables[0].markdown
    assert md.startswith("|")
    assert "品目" in md
    assert "マスター管理" in md
    assert "1,710,000" in md
    assert "| ---" in md
    titles = [r.markdown for r in result.regions if r.kind == "text"]
    assert "納品書" in titles
    assert "マスター管理" not in titles


def test_side_by_side_addresses_are_not_a_table():
    result = page_result_from_office_payload(
        {
            "text": "株式会社アルファ\n株式会社ベータ",
            "lines": [
                _line("株式会社アルファ", 40, 40, 220, 70),
                _line("株式会社ベータ", 400, 40, 580, 70),
            ],
        }
    )
    assert all(r.kind == "text" for r in result.regions)
    assert [r.markdown for r in result.regions] == ["株式会社アルファ", "株式会社ベータ"]


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
    # Cloudflare error 1010 bans Python-urllib's default User-Agent.
    assert "Python-urllib" not in captured["headers"]["User-Agent"]
    assert "DocuEngine-OCR" in captured["headers"]["User-Agent"]
    assert captured["headers"]["Accept"] == "application/json"
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


def test_cloudflare_1010_message_is_actionable():
    from app.ocr.sonasu_ocr import http_error_message

    message = http_error_message(403, "error code: 1010")
    assert "403" in message
    assert "1010" in message
    assert "Cloudflare" in message


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
