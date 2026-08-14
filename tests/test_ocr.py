"""Offline tests for tools/ocr.py: fake transport, mocked http, failures.

No test here touches the network: the http transport's post function is
monkeypatched with canned responses of the API's documented shape.
"""

import json

import pytest

from conftest import PAGE_ONE_LINES, load_tool


@pytest.fixture(scope="session")
def ocr_tool():
    return load_tool("ocr")


@pytest.fixture
def no_key(monkeypatch, tmp_path, ocr_tool):
    """No API key anywhere: not in the environment, no .env to fall back
    to. The developer checkout's real .env must never leak into a test."""
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    monkeypatch.setattr(ocr_tool, "ENV_FILE", tmp_path / "absent.env")


def canned_response(pages: int = 2) -> dict:
    return {
        "pages": [
            {
                "index": index,
                "markdown": (f"# Invented OCR heading {index + 1}\n\n"
                             f"Invented OCR body text for page "
                             f"{index + 1}."),
                "images": [{
                    "id": f"img-{index}.png",
                    "top_left_x": 100, "top_left_y": 200,
                    "bottom_right_x": 300, "bottom_right_y": 400,
                    "image_base64": "should-not-be-copied",
                }],
                "dimensions": {"dpi": 200, "height": 2200, "width": 1700},
            }
            for index in range(pages)
        ],
        "model": "mistral-ocr-latest",
        "usage_info": {"pages_processed": pages, "doc_size_bytes": 12345},
    }


def test_fake_transport_needs_no_key_and_no_network(ocr_tool, work_dir,
                                                    no_key):
    assert ocr_tool.main([str(work_dir), "--transport", "fake"]) == 0
    ocr_dir = work_dir / "ocr"
    assert (ocr_dir / "page_01.md").read_text(encoding="utf-8").count(
        PAGE_ONE_LINES[0]) == 1
    assert (ocr_dir / "page_02.md").is_file()
    meta = json.loads((ocr_dir / "meta.json").read_text(encoding="utf-8"))
    assert meta["transport"] == "fake"
    assert meta["usage"]["pages_processed"] == 2


def test_fake_transport_reports_the_pdf_image_bbox(ocr_tool, work_dir,
                                                   no_key):
    assert ocr_tool.main([str(work_dir), "--transport", "fake"]) == 0
    data = json.loads((work_dir / "ocr" / "images.json")
                      .read_text(encoding="utf-8"))
    page_one, page_two = data["pages"]
    assert page_one["page"] == 1 and page_one["images"] == []
    boxes = page_two["images"]
    assert len(boxes) == 1
    box = boxes[0]
    assert box["top_left_x"] < box["bottom_right_x"]
    assert box["top_left_y"] < box["bottom_right_y"]
    # The invented image was placed at (300, 400)-(380, 460) in PDF points.
    assert abs(box["top_left_x"] - 300) <= 2
    assert abs(box["bottom_right_y"] - 460) <= 2


def test_http_writes_the_response(ocr_tool, work_dir, monkeypatch):
    monkeypatch.setenv("MISTRAL_API_KEY", "invented-test-key")
    monkeypatch.setattr(ocr_tool, "_post_ocr",
                        lambda payload, api_key, timeout: canned_response())
    assert ocr_tool.main([str(work_dir)]) == 0
    ocr_dir = work_dir / "ocr"
    assert "# Invented OCR heading 1" in (ocr_dir / "page_01.md").read_text(
        encoding="utf-8")
    meta = json.loads((ocr_dir / "meta.json").read_text(encoding="utf-8"))
    assert meta["model"] == "mistral-ocr-latest"
    assert meta["transport"] == "http"
    assert meta["cost_estimate"]["total_usd"] == pytest.approx(0.002)
    data = json.loads((ocr_dir / "images.json").read_text(encoding="utf-8"))
    for page in data["pages"]:
        for image in page["images"]:
            assert "image_base64" not in image


def test_http_reads_the_key_from_the_env_file(ocr_tool, work_dir,
                                              monkeypatch, tmp_path):
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("MISTRAL_API_KEY=invented-file-key\n",
                        encoding="utf-8")
    monkeypatch.setattr(ocr_tool, "ENV_FILE", env_file)
    seen = {}

    def record(payload, api_key, timeout):
        seen["key"] = api_key
        return canned_response()

    monkeypatch.setattr(ocr_tool, "_post_ocr", record)
    assert ocr_tool.main([str(work_dir)]) == 0
    assert seen["key"] == "invented-file-key"


def test_http_without_a_key_fails_before_reading_anything(ocr_tool,
                                                          tmp_path, no_key,
                                                          capsys):
    # The work directory does not even exist: the key check comes first,
    # so the key failure is the one reported.
    assert ocr_tool.main([str(tmp_path / "absent")]) == 1
    assert "MISTRAL_API_KEY" in capsys.readouterr().err


def test_a_partial_reply_is_refused_whole(ocr_tool, work_dir, monkeypatch,
                                          capsys):
    monkeypatch.setenv("MISTRAL_API_KEY", "invented-test-key")
    monkeypatch.setattr(ocr_tool, "_post_ocr",
                        lambda payload, api_key, timeout:
                        canned_response(pages=1))
    assert ocr_tool.main([str(work_dir)]) == 1
    assert "partial witness" in capsys.readouterr().err
    assert not (work_dir / "ocr" / "page_01.md").exists()


def test_a_rate_limit_is_retried_once(ocr_tool, work_dir, monkeypatch):
    monkeypatch.setenv("MISTRAL_API_KEY", "invented-test-key")
    monkeypatch.setattr(ocr_tool.time, "sleep", lambda seconds: None)
    calls = {"count": 0}

    def flaky(payload, api_key, timeout):
        calls["count"] += 1
        if calls["count"] == 1:
            raise ocr_tool.OcrCallError("HTTP 429", status=429)
        return canned_response()

    monkeypatch.setattr(ocr_tool, "_post_ocr", flaky)
    assert ocr_tool.main([str(work_dir)]) == 0
    assert calls["count"] == 2


def test_a_client_error_is_not_retried(ocr_tool, work_dir, monkeypatch,
                                       capsys):
    monkeypatch.setenv("MISTRAL_API_KEY", "invented-test-key")
    calls = {"count": 0}

    def unauthorized(payload, api_key, timeout):
        calls["count"] += 1
        raise ocr_tool.OcrCallError("HTTP 401 unauthorized", status=401)

    monkeypatch.setattr(ocr_tool, "_post_ocr", unauthorized)
    assert ocr_tool.main([str(work_dir)]) == 1
    assert calls["count"] == 1
    assert "HTTP 401" in capsys.readouterr().err


def test_stale_page_files_are_replaced(ocr_tool, work_dir, no_key):
    ocr_dir = work_dir / "ocr"
    ocr_dir.mkdir()
    stale = ocr_dir / "page_99.md"
    stale.write_text("stale text from an earlier run\n", encoding="utf-8")
    assert ocr_tool.main([str(work_dir), "--transport", "fake"]) == 0
    assert not stale.exists()
