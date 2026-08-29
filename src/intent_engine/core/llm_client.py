"""Thin wrapper around the Anthropic API used by every pipeline stage.

Kept deliberately small: every stage should be able to swap this out (e.g. for a
local/open-source model) without changing its own logic, by depending only on
`call_tool`'s signature.
"""

import base64
import os
from pathlib import Path
from typing import Any, Dict, Optional, Union

from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

DEFAULT_MODEL = "claude-sonnet-5"

_IMAGE_MEDIA_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}


def _build_vision_content(image_path: Union[str, Path], text: str) -> list:
    path = Path(image_path)
    media_type = _IMAGE_MEDIA_TYPES.get(path.suffix.lower())
    if media_type is None:
        raise ValueError(f"Unsupported image type {path.suffix!r} for {path}")
    data = base64.standard_b64encode(path.read_bytes()).decode("utf-8")
    return [
        {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": data}},
        {"type": "text", "text": text},
    ]


class LLMClient:
    #: SECONDS ONE MODEL CALL MAY TAKE, and it has to be stated HERE because
    #: the SDK's own default is ten minutes.
    #:
    #: MEASURED on the deployed preview: an Apple analysis sat in "Mapping
    #: competitors" for 204s. `analyst/runner.py` declares
    #: REQUEST_TIMEOUT_S = 60.0 and MAX_ATTEMPTS = 2, which reads like a
    #: bounded call -- but the constant appeared exactly once in the whole
    #: tree, at its own definition, and was never passed to anything. The
    #: real bound was the SDK default of 600s, times the SDK's own two
    #: retries, times the runner's two attempts.
    #:
    #: `max_retries=0` because the runner already owns retry policy. Leaving
    #: the SDK's default of 2 in place makes the real attempt count four and
    #: hides half of them from the log that exists to explain them.
    DEFAULT_TIMEOUT_S = 60.0

    def __init__(self, model: str = DEFAULT_MODEL, api_key: Optional[str] = None,
                 timeout: Optional[float] = None):
        resolved_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not resolved_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set. Add it to a .env file (see .env.example) "
                "or pass api_key= explicitly."
            )
        self.timeout = float(self.DEFAULT_TIMEOUT_S if timeout is None
                             else timeout)
        self._client = Anthropic(api_key=resolved_key, timeout=self.timeout,
                                 max_retries=0)
        self.model = model

    def call_tool(
        self,
        *,
        system: str,
        user_message: str,
        tool_name: str,
        tool_description: str,
        input_schema: Dict[str, Any],
        max_tokens: int = 1024,
        image_path: Optional[Union[str, Path]] = None,
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Force the model to call `tool_name` and return its parsed input dict.

        image_path: if provided, attaches the image as a vision content block
        alongside user_message -- additive; every existing caller that never
        passes this is unaffected, since content stays a plain string unless
        image_path is given.
        """
        content = user_message if image_path is None else _build_vision_content(image_path, user_message)
        # A per-call override, so a caller holding an interactive budget can
        # spend what IT has left rather than what this client was built with.
        client = (self._client if timeout is None
                  else self._client.with_options(timeout=float(timeout)))
        response = client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": content}],
            tools=[
                {
                    "name": tool_name,
                    "description": tool_description,
                    "input_schema": input_schema,
                }
            ],
            tool_choice={"type": "tool", "name": tool_name},
        )
        if response.stop_reason == "max_tokens":
            raise RuntimeError(
                f"Response to tool '{tool_name}' was truncated at max_tokens={max_tokens} "
                f"(used {response.usage.output_tokens} output tokens). Raise max_tokens for "
                "this call or shorten the prompt's requested output."
            )
        for block in response.content:
            if block.type == "tool_use" and block.name == tool_name:
                return block.input
        raise RuntimeError(f"Model did not call tool '{tool_name}'. Response: {response.content}")
