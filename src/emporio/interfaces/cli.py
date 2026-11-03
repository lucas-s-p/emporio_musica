"""Command line chat: `emporio` or `python -m emporio`."""

import argparse
import logging
import sys
from collections.abc import Callable, Sequence
from datetime import date
from pathlib import Path

from emporio.agent import Agent, build_agent
from emporio.config import Settings
from emporio.data import load_store
from emporio.knowledge import load_policy_index
from emporio.llm import LLMConfigError, build_llm
from emporio.memory import Transcript
from emporio.services.clock import build_clock

WELCOME = (
    "Olá! Sou o atendente virtual da Empório da Música. "
    "Posso ajudar com produtos, preços, pagamento, frete, pedidos e trocas."
)
HELP = "Comandos: /novo (nova conversa), /ferramentas (mostra ou esconde as consultas), /sair"


def run_chat(
    new_agent: Callable[[], Agent],
    *,
    read: Callable[[str], str] = input,
    write: Callable[[str], None] = print,
    show_tools: bool = False,
    transcript: Transcript | None = None,
    save_path: Path | None = None,
) -> None:
    """Chat loop. Input and output are injected so it can be tested without a terminal."""
    agent = new_agent()
    write(WELCOME)
    write(HELP)
    while True:
        try:
            text = read("\nVocê: ").strip()
        except (EOFError, KeyboardInterrupt):
            write("")
            return
        if not text:
            continue
        command = text.lower()
        if command in ("/sair", "/exit", "/quit"):
            return
        if command == "/novo":
            agent = new_agent()
            if transcript:
                transcript.new_conversation()
            write("Nova conversa iniciada.")
            continue
        if command == "/ferramentas":
            show_tools = not show_tools
            write(f"Consultas {'visíveis' if show_tools else 'ocultas'}.")
            continue
        reply = agent.respond(text)
        if show_tools:
            for trace in reply.tool_traces:
                preview = trace.result if len(trace.result) <= 160 else trace.result[:160] + "..."
                write(f"  [ferramenta] {trace.name}({trace.arguments}) -> {preview}")
        write(f"\nAgente: {reply.text}")
        if transcript:
            transcript.add(text, reply)
            if save_path:
                transcript.save(save_path)  # after every turn, so a crash loses nothing


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="emporio", description="Atendente da Empório da Música")
    parser.add_argument("--today", type=date.fromisoformat, help="fixa a data de hoje (AAAA-MM-DD)")
    parser.add_argument("--tools", action="store_true", help="mostra as consultas às ferramentas")
    parser.add_argument("--save", type=Path, help="grava a conversa em Markdown neste arquivo")
    parser.add_argument("-v", "--verbose", action="store_true", help="log de retries e fallbacks")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING, format="%(levelname)s %(message)s"
    )
    settings = Settings()
    try:
        llm = build_llm(settings)
    except LLMConfigError as exc:
        print(f"Configuração incompleta: {exc}", file=sys.stderr)
        print("Copie .env.example para .env e preencha OPENROUTER_API_KEY.", file=sys.stderr)
        return 2
    store = load_store(settings.data_dir)
    policies = load_policy_index(settings.data_dir)
    clock = build_clock(args.today or settings.store_today)

    transcript = Transcript() if args.save else None
    run_chat(
        lambda: build_agent(llm, store, clock, policies, settings.prompts_dir),
        show_tools=args.tools,
        transcript=transcript,
        save_path=args.save,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
