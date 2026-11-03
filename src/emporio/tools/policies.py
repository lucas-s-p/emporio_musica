"""Policy tool: search the store manual. Rules that need numbers or dates live in other tools."""

from pydantic import Field

from emporio.knowledge import PolicyIndex
from emporio.tools.base import JsonDict, Tool, ToolInput


class SearchPoliciesInput(ToolInput):
    query: str = Field(
        min_length=3,
        description="What the customer wants to know, in Portuguese. "
        "E.g. 'prazo para devolver', 'troca por defeito', 'formas de pagamento'.",
    )
    limit: int = Field(default=3, ge=1, le=5)


def _search(index: PolicyIndex, args: SearchPoliciesInput) -> JsonDict:
    hits = index.search(args.query, args.limit)
    if not hits:
        return {
            "results": [],
            "error": "NOT_IN_POLICIES",
            "hint": "The manual says nothing about this. Do not guess: say you do not have "
            "this information and offer the store contact (get_store_info).",
        }
    return {
        "results": [
            {
                "section": hit.section.section_id,
                "path": hit.section.path,
                "page": hit.section.page,
                "text": hit.section.text,
                "score": hit.score,
                **({"note": hit.note} if hit.note else {}),
            }
            for hit in hits
        ],
        "source": "Manual de Políticas e Procedimentos, versão 2.1 (junho de 2025)",
    }


def policy_tools(index: PolicyIndex) -> list[Tool]:
    return [
        Tool(
            name="search_policies",
            description=(
                "Search the store policy manual: payment, installments, returns and exchanges, "
                "shipping, promotions, warranty, privacy, opening hours and service rules. "
                "Use it for any 'how does X work' question. Sections with a 'note' contain a "
                "known conflict: follow the note. For exact prices, totals, deadlines of a "
                "specific order or opening status, use the data tools instead."
            ),
            input_model=SearchPoliciesInput,
            handler=lambda args: _search(index, args),
        )
    ]
