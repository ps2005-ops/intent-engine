import base64
from unittest.mock import MagicMock, patch

import pytest

from intent_engine.core.llm_client import LLMClient, _build_vision_content


def test_build_vision_content_encodes_png_correctly(tmp_path):
    image_path = tmp_path / "test.png"
    image_path.write_bytes(b"fake-png-bytes")

    content = _build_vision_content(image_path, "check this")

    assert len(content) == 2
    assert content[0]["type"] == "image"
    assert content[0]["source"]["media_type"] == "image/png"
    assert content[0]["source"]["data"] == base64.standard_b64encode(b"fake-png-bytes").decode("utf-8")
    assert content[1] == {"type": "text", "text": "check this"}


def test_build_vision_content_maps_jpeg_media_type(tmp_path):
    image_path = tmp_path / "test.jpg"
    image_path.write_bytes(b"fake-jpg-bytes")

    content = _build_vision_content(image_path, "check this")

    assert content[0]["source"]["media_type"] == "image/jpeg"


def test_build_vision_content_rejects_unsupported_extension(tmp_path):
    image_path = tmp_path / "test.bmp"
    image_path.write_bytes(b"fake-bmp-bytes")

    with pytest.raises(ValueError):
        _build_vision_content(image_path, "check this")


def _mock_anthropic_response(tool_name, tool_input):
    block = MagicMock()
    block.type = "tool_use"
    block.name = tool_name
    block.input = tool_input
    response = MagicMock()
    response.stop_reason = "tool_use"
    response.content = [block]
    return response


@patch("intent_engine.core.llm_client.Anthropic")
def test_call_tool_without_image_path_sends_plain_string_content(mock_anthropic_cls):
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _mock_anthropic_response("record", {"x": 1})
    mock_anthropic_cls.return_value = mock_client

    client = LLMClient(api_key="fake-key")
    client.call_tool(
        system="sys", user_message="hello", tool_name="record", tool_description="d",
        input_schema={"type": "object", "properties": {}},
    )

    sent_messages = mock_client.messages.create.call_args.kwargs["messages"]
    assert sent_messages == [{"role": "user", "content": "hello"}]


@patch("intent_engine.core.llm_client.Anthropic")
def test_call_tool_with_image_path_sends_vision_content_blocks(mock_anthropic_cls, tmp_path):
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _mock_anthropic_response("record", {"x": 1})
    mock_anthropic_cls.return_value = mock_client

    image_path = tmp_path / "test.png"
    image_path.write_bytes(b"fake-png-bytes")

    client = LLMClient(api_key="fake-key")
    client.call_tool(
        system="sys", user_message="check this", tool_name="record", tool_description="d",
        input_schema={"type": "object", "properties": {}}, image_path=image_path,
    )

    sent_content = mock_client.messages.create.call_args.kwargs["messages"][0]["content"]
    assert sent_content[0]["type"] == "image"
    assert sent_content[1] == {"type": "text", "text": "check this"}
