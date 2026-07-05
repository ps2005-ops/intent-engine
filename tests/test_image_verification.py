from unittest.mock import MagicMock

from intent_engine.core.image_verification import (
    VerificationResult,
    render_verification_as_text,
    verify_image,
)

CHECKLIST = ["Vendor name visible", "Date visible", "Amount visible"]


def _fake_client(tool_input):
    client = MagicMock()
    client.call_tool.return_value = tool_input
    return client


def test_verify_image_returns_complete_verdict_with_empty_missing(tmp_path):
    image_path = tmp_path / "fake.png"
    image_path.write_bytes(b"fake-bytes")
    client = _fake_client({
        "verdict": "complete", "missing": [], "reasoning": "all fields visible", "confidence": "high",
    })

    result = verify_image(image_path, CHECKLIST, client=client)

    assert isinstance(result, VerificationResult)
    assert result.verdict == "complete"
    assert result.missing == []
    assert result.confidence == "high"


def test_verify_image_returns_incomplete_with_missing_items(tmp_path):
    image_path = tmp_path / "fake.png"
    image_path.write_bytes(b"fake-bytes")
    client = _fake_client({
        "verdict": "incomplete", "missing": ["Date visible"], "reasoning": "date not shown", "confidence": "medium",
    })

    result = verify_image(image_path, CHECKLIST, client=client)

    assert result.verdict == "incomplete"
    assert result.missing == ["Date visible"]


def test_verify_image_returns_illegible(tmp_path):
    image_path = tmp_path / "fake.png"
    image_path.write_bytes(b"fake-bytes")
    client = _fake_client({
        "verdict": "illegible", "missing": CHECKLIST, "reasoning": "image too blurry to read", "confidence": "low",
    })

    result = verify_image(image_path, CHECKLIST, client=client)

    assert result.verdict == "illegible"
    assert result.missing == CHECKLIST


def test_verify_image_passes_image_path_through_to_call_tool(tmp_path):
    image_path = tmp_path / "fake.png"
    image_path.write_bytes(b"fake-bytes")
    client = _fake_client({"verdict": "complete", "missing": [], "reasoning": "ok", "confidence": "high"})

    verify_image(image_path, CHECKLIST, client=client)

    assert client.call_tool.call_args.kwargs["image_path"] == image_path


def test_verify_image_checklist_appears_in_user_message(tmp_path):
    image_path = tmp_path / "fake.png"
    image_path.write_bytes(b"fake-bytes")
    client = _fake_client({"verdict": "complete", "missing": [], "reasoning": "ok", "confidence": "high"})

    verify_image(image_path, CHECKLIST, client=client)

    user_message = client.call_tool.call_args.kwargs["user_message"]
    for item in CHECKLIST:
        assert item in user_message


def test_render_verification_as_text_includes_verdict_and_reasoning():
    result = VerificationResult(verdict="incomplete", missing=["Date visible"], reasoning="date not shown", confidence="medium")

    text = render_verification_as_text(result)

    assert "incomplete" in text
    assert "Date visible" in text
    assert "date not shown" in text


def test_render_verification_as_text_handles_empty_missing_list():
    result = VerificationResult(verdict="complete", missing=[], reasoning="all fields visible", confidence="high")

    text = render_verification_as_text(result)

    assert "none" in text.lower()
