"""Lexical retrieval (BM25) over the policy sections.

Why not embeddings: the manual has about 25 short sections and the free OpenRouter models
offer no stable embedding endpoint. BM25 is deterministic, offline, free and easy to test.
A small expansion table bridges the gap between how customers talk and how the manual does.
"""

import math
import re
from collections import Counter
from dataclasses import dataclass

from emporio.data.cleaning import normalize_text
from emporio.knowledge.errata import ERRATA
from emporio.knowledge.policies import PolicySection

K1 = 1.5
B = 0.75
EXPANSION_WEIGHT = 0.5
MIN_SCORE = 2.5  # below this a match is noise (e.g. 'tempo' in 'tempo de resposta')
RELATIVE_CUTOFF = 0.35  # drop hits far weaker than the best one

_STOPWORDS = frozenset(
    "de do da dos das um uma uns umas para pra com sem por em no na nos nas o a os as e ou "
    "que qual quais como quando onde posso pode podem preciso quero queria fazer ter tem "
    "tenho voces voce eu meu minha me se entre sobre ate".split()
)  # fmt: skip


def stem(word: str) -> str:
    """Crude Portuguese stemmer: singular, then a 5-letter prefix (devolver, devolução: devol)."""
    if word.endswith("oes") and len(word) > 4:
        word = word[:-3] + "ao"
    elif word.endswith("s") and len(word) > 3:
        word = word[:-1]
    return word[:5]


def tokenize(text: str) -> list[str]:
    words = re.findall(r"[a-z0-9]+", normalize_text(text))
    return [stem(w) for w in words if w not in _STOPWORDS and not (w.isdigit() and len(w) < 3)]


def _expansions() -> dict[str, list[str]]:
    raw = {
        "devolver": "arrependimento reembolso troca",
        "devolucao": "arrependimento reembolso",
        "arrependi": "devolucao reembolso",
        "reembolso": "devolucao arrependimento",
        "estorno": "reembolso devolucao",
        "trocar": "troca preferencia defeito",
        "defeito": "garantia troca fabricacao",
        "quebrou": "defeito garantia",
        "estragou": "defeito garantia",
        "pagar": "pagamento pix cartao boleto parcelamento",
        "parcelar": "parcelamento cartao credito",
        "comprar": "pagamento frete",
        "entregar": "entrega frete prazo",
        "chegar": "entrega prazo frete",
        "demora": "prazo entrega",
        "rastrear": "rastreamento codigo",
        "rastreio": "rastreamento codigo",
        "abre": "horario funcionamento",
        "fecha": "horario funcionamento",
        "aberto": "horario funcionamento",
        "funciona": "horario funcionamento",
        "desconto": "promocao pix",
        "oferta": "promocao desconto",
        "lgpd": "privacidade dados",
        "excluir": "dados privacidade",
        "acessorio": "comercializamos exclusivamente instrumentos redirecionados",
        "corda": "acessorios comercializamos",
        "cabo": "acessorios comercializamos",
        "palheta": "acessorios comercializamos",
        "pedal": "acessorios comercializamos",
        "amplificador": "acessorios comercializamos",
        "case": "acessorios comercializamos",
        "reclamacao": "reclamacao responsavel retorno",
        "endereco": "dados empresa endereco",
        "telefone": "dados empresa whatsapp",
        "whatsapp": "atendimento whatsapp telefone",
    }
    return {stem(key): tokenize(values) for key, values in raw.items()}


EXPANSIONS = _expansions()


@dataclass(frozen=True)
class PolicyHit:
    section: PolicySection
    score: float
    note: str | None


class PolicyIndex:
    def __init__(self, sections: list[PolicySection]) -> None:
        if not sections:
            raise ValueError("No policy sections to index")
        self.sections = sections
        self._tf: list[Counter[str]] = []
        for section in sections:
            # The heading path counts three times: "Trocas por Defeito" should win on "defeito".
            self._tf.append(
                Counter(tokenize(f"{section.path} {section.path} {section.path} {section.text}"))
            )
        self._lengths = [sum(tf.values()) for tf in self._tf]
        self._avg_length = sum(self._lengths) / len(self._lengths)
        self._df: Counter[str] = Counter()
        for tf in self._tf:
            self._df.update(tf.keys())

    def get(self, section_id: str) -> PolicySection | None:
        return next((s for s in self.sections if s.section_id == section_id), None)

    def search(self, query: str, limit: int = 3) -> list[PolicyHit]:
        weights: dict[str, float] = {}
        for term in tokenize(query):
            weights[term] = max(weights.get(term, 0.0), 1.0)
            for extra in EXPANSIONS.get(term, []):
                weights[extra] = max(weights.get(extra, 0.0), EXPANSION_WEIGHT)

        scored: list[tuple[float, int]] = []
        total = len(self.sections)
        for index, tf in enumerate(self._tf):
            score = 0.0
            norm = K1 * (1 - B + B * self._lengths[index] / self._avg_length)
            for term, weight in weights.items():
                freq = tf.get(term, 0)
                if not freq:
                    continue
                df = self._df[term]
                idf = math.log(1 + (total - df + 0.5) / (df + 0.5))
                score += weight * idf * freq * (K1 + 1) / (freq + norm)
            if score > 0:
                scored.append((score, index))

        scored.sort(key=lambda pair: (-pair[0], pair[1]))
        if not scored or scored[0][0] < MIN_SCORE:
            return []
        best = scored[0][0]
        keep = [(s, i) for s, i in scored if s >= MIN_SCORE and s >= best * RELATIVE_CUTOFF]
        return [
            PolicyHit(self.sections[i], round(score, 3), ERRATA.get(self.sections[i].section_id))
            for score, i in keep[:limit]
        ]
