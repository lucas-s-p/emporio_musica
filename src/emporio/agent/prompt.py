"""System prompt: the persona lives in prompts/persona.md, "today" is injected from the clock."""

from pathlib import Path

from emporio.services.clock import Clock

_WEEKDAYS = (
    "segunda-feira",
    "terça-feira",
    "quarta-feira",
    "quinta-feira",
    "sexta-feira",
    "sábado",
    "domingo",
)


def persona_path(prompts_dir: Path) -> Path:
    return prompts_dir / "persona.md"


def build_system_prompt(clock: Clock, prompts_dir: Path) -> str:
    template = persona_path(prompts_dir).read_text(encoding="utf-8")
    today = clock.today()
    # Plain replace, not str.format: the persona may contain literal braces.
    return template.replace("{today}", today.strftime("%d/%m/%Y")).replace(
        "{weekday}", _WEEKDAYS[today.weekday()]
    )
