"""Parse the policy manual (PDF) into one chunk per section, with the heading path kept."""

import re
from dataclasses import dataclass
from pathlib import Path

import pymupdf

_NOISE = re.compile(
    r"^(Empório da Música Manual de Políticas e Procedimentos|Página \d+"
    r"|Empório da Música — Sua música começa aqui\.|Última atualização:.*)$"
)
# "4.2 Trocas por Defeito" or "4. Política ...". The title must start with a capital letter,
# which keeps table cells such as "5 a 12 dias úteis" from being read as headings.
_HEADING = re.compile(r"^(\d+)(?:\.(\d+))?\.?\s+([A-ZÀ-Ú].*)$")
_SENTENCE_END = (".", ":", ";", "?", "!")


@dataclass(frozen=True)
class PolicySection:
    section_id: str  # "4.2" for a subsection, "4" for the intro of a top-level section
    title: str
    path: str  # "4. Política de Trocas e Devoluções > 4.2 Trocas por Defeito"
    text: str
    page: int


def policy_pdf_path(data_dir: Path) -> Path:
    """The manual inside data_dir. Globbed because the file name has an accent."""
    matches = sorted(data_dir.glob("pol*.pdf"))
    if not matches:
        raise FileNotFoundError(f"Policy PDF not found in {data_dir}")
    return matches[0]


def _page_lines(pdf_path: Path) -> list[tuple[int, str]]:
    lines: list[tuple[int, str]] = []
    with pymupdf.open(pdf_path) as document:
        for number, page in enumerate(document, start=1):
            for raw in page.get_text().splitlines():
                line = raw.replace("\u200b", "").strip()
                if line and not _NOISE.match(line):
                    lines.append((number, line))
    return lines


def _tidy(lines: list[str]) -> str:
    """Join wrapped bullet items. Table cells and prose lines are kept one per line."""
    out: list[str] = []
    pending_bullet = False
    for line in lines:
        if line == "•":
            pending_bullet = True
            continue
        if pending_bullet:
            out.append(f"• {line}")
            pending_bullet = False
        elif out and out[-1].startswith("• ") and not out[-1].endswith(_SENTENCE_END):
            out[-1] = f"{out[-1]} {line}"
        else:
            out.append(line)
    return "\n".join(out)


def parse_policies(pdf_path: Path) -> list[PolicySection]:
    """Split the manual into sections. Everything before section 1 (the cover) is dropped."""
    sections: list[PolicySection] = []
    top = sub = 0
    top_title = ""
    current: dict[str, object] | None = None

    def close() -> None:
        if current and (body := _tidy(current["lines"])):  # type: ignore[arg-type]
            sections.append(
                PolicySection(
                    section_id=str(current["id"]),
                    title=str(current["title"]),
                    path=str(current["path"]),
                    text=body,
                    page=int(current["page"]),  # type: ignore[call-overload]
                )
            )

    for page, line in _page_lines(pdf_path):
        match = _HEADING.match(line)
        major = int(match.group(1)) if match else 0
        minor = int(match.group(2)) if match and match.group(2) else None
        is_top = bool(match) and minor is None and major == top + 1
        is_sub = bool(match) and minor is not None and major == top and minor == sub + 1
        if match and (is_top or is_sub):
            close()
            title = match.group(3).strip()
            if is_top:
                top, sub, top_title = major, 0, f"{major}. {title}"
                current = {"id": str(major), "title": title, "path": top_title, "page": page}
            else:
                sub = minor or 0
                heading = f"{major}.{sub} {title}"
                current = {
                    "id": f"{major}.{sub}",
                    "title": title,
                    "path": f"{top_title} > {heading}",
                    "page": page,
                }
            current["lines"] = []
        elif current is not None:
            current["lines"].append(line)  # type: ignore[attr-defined]
    close()
    return sections
