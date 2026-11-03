"""Tool framework: typed inputs, JSON Schema for the LLM and safe dispatch.

Tool handlers never raise to the caller: every failure becomes {"error": CODE, ...}, so the
model always gets something it can act on and no stack trace leaks into the conversation.
"""

import json
import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

logger = logging.getLogger(__name__)

JsonDict = dict[str, Any]


class ToolInput(BaseModel):
    """Base for tool arguments. Unknown arguments are rejected instead of silently ignored."""

    model_config = ConfigDict(extra="forbid")


class ToolError(Exception):
    """A business-level failure the model should see (e.g. NOT_VERIFIED)."""

    def __init__(self, code: str, **details: Any) -> None:
        super().__init__(code)
        self.code = code
        self.details = details


def _simplify(node: Any, defs: JsonDict) -> Any:
    """Inline $ref, collapse Optional[X] and drop noise, for models with weak schema support."""
    if isinstance(node, list):
        return [_simplify(item, defs) for item in node]
    if not isinstance(node, dict):
        return node
    if "$ref" in node:
        target = defs[node["$ref"].rsplit("/", 1)[-1]]
        siblings = {k: v for k, v in node.items() if k != "$ref"}
        return _simplify({**target, **siblings}, defs)
    options = node.get("anyOf")
    if options:
        non_null = [o for o in options if o.get("type") != "null"]
        if len(non_null) == 1:
            rest = {k: v for k, v in node.items() if k != "anyOf"}
            return _simplify({**non_null[0], **rest}, defs)
    out: JsonDict = {}
    for key, value in node.items():
        if key == "properties":
            out[key] = {name: _simplify(sub, defs) for name, sub in value.items()}
        elif key in ("title", "$defs") or (key == "default" and value is None):
            continue
        else:
            out[key] = _simplify(value, defs)
    return out


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    input_model: type[ToolInput]
    handler: Callable[[Any], JsonDict]

    def spec(self) -> JsonDict:
        schema = self.input_model.model_json_schema()
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": _simplify(schema, schema.get("$defs", {})),
            },
        }


class ToolRegistry:
    def __init__(self, tools: Iterable[Tool]) -> None:
        self._tools: dict[str, Tool] = {}
        for tool in tools:
            if tool.name in self._tools:
                raise ValueError(f"Duplicate tool name: {tool.name}")
            self._tools[tool.name] = tool

    @property
    def names(self) -> list[str]:
        return list(self._tools)

    def specs(self) -> list[JsonDict]:
        """Tool definitions in the OpenAI-compatible `tools` format."""
        return [tool.spec() for tool in self._tools.values()]

    def execute(self, name: str, arguments: str | JsonDict | None = None) -> JsonDict:
        tool = self._tools.get(name)
        if tool is None:
            return {"error": "UNKNOWN_TOOL", "available_tools": self.names}
        try:
            raw = self._parse_arguments(arguments)
            parsed = tool.input_model.model_validate(raw)
            return tool.handler(parsed)
        except ToolError as exc:
            return {"error": exc.code, **exc.details}
        except ValidationError as exc:
            problems = [
                {"field": ".".join(str(p) for p in e["loc"]), "problem": e["msg"]}
                for e in exc.errors()
            ]
            return {"error": "INVALID_ARGUMENTS", "problems": problems}
        except ValueError as exc:  # malformed JSON from the model
            return {"error": "INVALID_ARGUMENTS", "problems": [{"field": "", "problem": str(exc)}]}
        except Exception:
            logger.exception("Tool %s failed", name)
            return {"error": "INTERNAL_ERROR"}

    def execute_json(self, name: str, arguments: str | JsonDict | None = None) -> str:
        """Same as execute, serialized for the `tool` message content (full, never truncated)."""
        return json.dumps(self.execute(name, arguments), ensure_ascii=False)

    @staticmethod
    def _parse_arguments(arguments: str | JsonDict | None) -> JsonDict:
        if arguments is None or arguments == "":
            return {}
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Arguments are not valid JSON: {exc.msg}") from exc
        if not isinstance(arguments, dict):
            raise ValueError("Arguments must be a JSON object")
        return arguments
