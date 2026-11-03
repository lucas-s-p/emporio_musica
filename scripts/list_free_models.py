"""Lists the OpenRouter models that are free and advertise tool support.

Usage: uv run python scripts/list_free_models.py
The models endpoint is public (no key needed). Run it before setting OPENROUTER_MODEL, since
free models change often.
"""

import json
import sys
import urllib.request

URL = "https://openrouter.ai/api/v1/models"


def main() -> int:
    with urllib.request.urlopen(URL, timeout=30) as resp:
        models = json.load(resp)["data"]
    rows = []
    for m in models:
        pricing = m.get("pricing", {})
        free = all(float(pricing.get(k) or 0) == 0 for k in ("prompt", "completion"))
        params = m.get("supported_parameters") or []
        if free and "tools" in params:
            rows.append((m["id"], m.get("context_length", 0), "tool_choice" in params))
    for model_id, ctx, choice in sorted(rows):
        print(f"{model_id:60} ctx={ctx:>8} tool_choice={choice}")
    print(f"\n{len(rows)} free models with tools", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
