"""Runs the example conversations against the real agent and saves them in examples/.

    python scripts/generate_examples.py                 # all scenarios
    python scripts/generate_examples.py --only 04       # one scenario (matches the file prefix)
    python scripts/generate_examples.py --list

Each scenario gets a fresh agent and its own pinned "today", so the files are reproducible
in the data they use (the model's wording will vary between runs). A scenario whose turn fell
back to the canned outage message is NOT saved, so a rate-limited run never overwrites a good
example. Small automatic checks print OK or ATENCAO per turn; read the saved files anyway.

Free OpenRouter models allow few requests per day: if the quota runs out, wait and run the
missing scenarios with --only.
"""

import argparse
import sys
import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from emporio.agent import build_agent
from emporio.agent.agent import AgentReply
from emporio.config import Settings
from emporio.data import load_store
from emporio.knowledge import load_policy_index
from emporio.llm import LLMClient, LLMConfigError, build_llm
from emporio.memory import Transcript
from emporio.services.clock import build_clock


@dataclass(frozen=True)
class Turn:
    text: str
    tools: tuple[str, ...] = ()  # tools that must have been called
    no_tools: bool = False  # the agent must not have called any tool
    contains: tuple[str, ...] = ()  # each must appear in the answer (case-insensitive)


@dataclass(frozen=True)
class Scenario:
    slug: str  # file name: examples/<slug>.md
    title: str
    today: date
    turns: list[Turn] = field(default_factory=list)


SCENARIOS = [
    Scenario(
        "01-catalogo-violoes",
        "Catálogo: violões até R$ 1.000",
        date(2026, 11, 2),
        [
            Turn(
                "Quais opções de violões disponíveis custando até R$1000?",
                tools=("search_products",),
            )
        ],
    ),
    Scenario(
        "02-loja-endereco-e-horario",
        "Informações da loja: endereço e horário",
        date(2026, 11, 2),  # Finados, feriado nacional: a loja está fechada
        [
            Turn("Qual o endereço da loja?", tools=("get_store_info",), contains=("14 de Maio",)),
            Turn("Vocês estão abertos hoje?", tools=("get_store_info",), contains=("fechad",)),
        ],
    ),
    Scenario(
        "03-preco-e-parcelamento-takamine",
        "Preço e parcelamento: Takamine GD20",
        date(2026, 11, 2),
        [
            Turn(
                "Quanto custa o Takamine GD20?", tools=("search_products",), contains=("2.199,00",)
            ),
            Turn(
                "E no cartão, em 10x, quanto fica cada parcela?",
                tools=("get_payment_options",),
                contains=("219,90",),
            ),
        ],
    ),
    Scenario(
        "04-devolucao-por-arrependimento",
        "Política de devolução: arrependimento (cliente verificado)",
        date(2026, 1, 22),  # pedido 5 entregue em 18/01/2026: ainda dentro do prazo de 7 dias
        [
            Turn("Me arrependi da minha compra, posso devolver meu pedido?", no_tools=True),
            Turn(
                "Meu e-mail é rafael.pereira@jmail.com e o pedido é o 5.",
                tools=("verify_customer", "check_return_eligibility"),
                contains=("25/01/2026",),
            ),
        ],
    ),
    Scenario(
        "05-fora-de-escopo-e-acessorios",
        "Fora de escopo e produto que a loja não vende",
        date(2026, 11, 2),
        [
            Turn("Me ajuda a escrever um código em Python que ordena uma lista?", no_tools=True),
            Turn("Vocês vendem palheta e corda de violão?", contains=("não",)),
        ],
    ),
]


def check(turn: Turn, reply: AgentReply) -> list[str]:
    """Problems found in one answer (empty list means all checks passed)."""
    called = [t.name for t in reply.tool_traces]
    problems = [f"não chamou {name}" for name in turn.tools if name not in called]
    if turn.no_tools and called:
        problems.append(f"chamou ferramentas ({', '.join(called)}) quando não devia")
    text = reply.text.lower()
    problems += [f"resposta sem '{s}'" for s in turn.contains if s.lower() not in text]
    return problems


def run_scenario(
    scenario: Scenario, settings: Settings, llm: LLMClient, pause: float
) -> tuple[Transcript | None, bool]:
    """Returns (transcript or None when degraded, all checks passed)."""
    store = load_store(settings.data_dir)
    policies = load_policy_index(settings.data_dir)
    clock = build_clock(scenario.today)
    agent = build_agent(llm, store, clock, policies, settings.prompts_dir)
    transcript = Transcript(title=scenario.title)
    models: list[str] = []
    all_ok = True
    for i, turn in enumerate(scenario.turns):
        if i:
            time.sleep(pause)  # stay under the free tier's per-minute limit
        reply = agent.respond(turn.text)
        print(f"  > {turn.text}")
        if reply.degraded:
            print("    FALHOU: o modelo não respondeu (cota ou indisponibilidade). Não salvo.")
            return None, False
        transcript.add(turn.text, reply)
        if reply.model and reply.model not in models:
            models.append(reply.model)
        problems = check(turn, reply)
        all_ok &= not problems
        print("    OK" if not problems else f"    ATENCAO: {'; '.join(problems)}")
    transcript.subtitle = (
        f"Data de hoje fixada em {scenario.today.strftime('%d/%m/%Y')}. "
        f"Modelo: {', '.join(models) or 'desconhecido'}. "
        "Gerado por scripts/generate_examples.py."
    )
    return transcript, all_ok


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--only", help="roda só os cenários cujo nome começa com este texto")
    parser.add_argument("--list", action="store_true", help="lista os cenários e sai")
    parser.add_argument("--out", type=Path, default=Path("examples"), help="pasta de saída")
    parser.add_argument("--pause", type=float, default=4.0, help="segundos entre perguntas")
    args = parser.parse_args()

    chosen = [s for s in SCENARIOS if not args.only or s.slug.startswith(args.only)]
    if args.list or not chosen:
        for s in SCENARIOS:
            print(f"{s.slug}  ({len(s.turns)} pergunta(s), hoje = {s.today})")
        return 0 if chosen else 1

    settings = Settings()
    try:
        llm = build_llm(settings)
    except LLMConfigError as exc:
        print(f"Configuração incompleta: {exc}", file=sys.stderr)
        return 2

    failed: list[str] = []
    for scenario in chosen:
        print(f"\n[{scenario.slug}] {scenario.title}")
        transcript, ok = run_scenario(scenario, settings, llm, args.pause)
        if transcript is None:
            failed.append(scenario.slug)
            continue
        transcript.save(args.out / f"{scenario.slug}.md")
        print(f"    salvo em {args.out / (scenario.slug + '.md')}")
        if not ok:
            failed.append(scenario.slug + " (checagens)")

    print("\nTudo certo." if not failed else f"\nRevisar: {', '.join(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
