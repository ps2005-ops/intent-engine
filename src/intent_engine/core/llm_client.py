"""Thin wrapper around the Anthropic API used by every pipeline stage.

Kept deliberately small: every stage should be able to swap this out (e.g. for a
local/open-source model) without changing its own logic, by depending only on
`call_tool`'s signature.
"""

import os
from typing import Any, Dict, Optional

from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

DEFAULT_MODEL = "claude-sonnet-5"


class LLMClient:
    def __init__(self, model: str = DEFAULT_MODEL, api_key: Optional[str] = None):
        resolved_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not resolved_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set. Add it to a .env file (see .env.example) "
                "or pass api_key= explicitly."
            )
        self._client = Anthropic(api_key=resolved_key)
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
    ) -> Dict[str, Any]:
        """Force the model to call `tool_name` and return its parsed input dict."""
        response = self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user_message}],
            tools=[
                {
                    "name": tool_name,
                    "description": tool_description,
                    "input_schema": input_schema,
                }
            ],
            tool_choice={"type": "tool", "name": tool_name},
        )
        for block in response.content:
            if block.type == "tool_use" and block.name == tool_name:
                return block.input
        raise RuntimeError(f"Model did not call tool '{tool_name}'. Response: {response.content}")
