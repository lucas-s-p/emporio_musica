# Empório da Música: agente de atendimento

Agente de atendimento por texto para a Empório da Música, loja de instrumentos musicais de Campo Grande, MS. Feito para o desafio técnico de AI Engineer (Artefact).

O agente consulta os dados da loja por ferramentas (produtos, preços, parcelamento, frete, pedidos, devoluções, políticas) e recusa o que está fora do escopo. Todo cálculo é realizado em Python e devolvido por uma ferramenta, nunca pelo modelo.

## Como rodar

Requisitos: Python 3.11 ou mais novo e [uv](https://docs.astral.sh/uv/) (ou `pip`).

```bash
git clone <este repositório> && cd emporio_musica
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"        # ou: pip install -e ".[dev]"
```

A instalação precisa ser editável (`-e`): o programa acha `data/`, `prompts/` e `.env` a partir da raiz do projeto, então pode ser executado de qualquer pasta.

### Chave do OpenRouter

O agente usa o [OpenRouter](https://openrouter.ai) (API compatível com a da OpenAI) e modelos gratuitos.

1. Crie uma conta gratuita em https://openrouter.ai e gere uma chave em https://openrouter.ai/keys.
2. `cp .env.example .env` e preencha `OPENROUTER_API_KEY` no `.env` (o arquivo está no `.gitignore`).
3. Ajuste `OPENROUTER_MODEL` e `OPENROUTER_FALLBACK_MODELS`.

### Conversar com o agente

```bash
python -m emporio                              
python -m emporio --today 2026-11-02 --tools       # fixa a data e mostra as consultas às ferramentas
python -m emporio --save examples/minha-conversa.md
```

Comandos dentro do chat: `/novo` (nova conversa, sem identidade nem histórico), `/ferramentas` (mostra ou esconde as consultas), `/sair`. A opção `-v` mostra os retries e as trocas de modelo.

### Testes e qualidade

```bash
python -m pytest -q                 # 214 testes, sem rede e sem chave (o LLM é simulado)
ruff check src tests scripts && mypy src
```

## Como funciona

```
Cliente → CLI → Agent ──► LLMClient (OpenRouter, com retry e fallback)
                  │
                  └─► ToolRegistry ─► services (regras em Python) ─► data (CSVs) / knowledge (PDF)
```

| Camada | Pasta | Papel |
|---|---|---|
| config | `config.py` | Variáveis de ambiente e `.env`, caminhos ancorados na raiz do projeto |
| data | `data/`, `domain/` | Leitura dos CSVs, validação com Pydantic, checagens de qualidade |
| services | `services/` | Regras determinísticas: catálogo, preço, parcelamento, frete, horário, identidade, devolução |
| tools | `tools/` | 9 ferramentas com entrada tipada e JSON Schema para o modelo |
| knowledge | `knowledge/` | Manual de políticas (PDF) dividido em seções, com busca BM25 |
| llm | `llm/` | Interface abstrata `LLMClient`; OpenRouter é uma implementação |
| agent | `agent/`, `prompts/persona.md` | Loop de tool calling e persona em arquivo |
| memory | `memory/` | Histórico limitado e transcrição em Markdown |
| interfaces | `interfaces/` | CLI |

Ferramentas: `search_products`, `get_product`, `get_payment_options`, `estimate_shipping`, `get_store_info`, `verify_customer`, `get_order_status`, `check_return_eligibility`, `search_policies`.

## Decisões e justificativas

- **Function calling com regras em Python.** O modelo escolhe qual ferramenta chamar e redige a resposta. Preço, parcelas, frete, prazo de devolução e horário vêm de código testado. Isso evita erro de conta e dado inventado, e deixa cada regra com teste.
- **Segurança em código, não no prompt.** Um pedido só é lido pelo verificador da conversa, e "pedido inexistente" e "pedido de outro cliente" têm a mesma resposta. A verificação trava após 3 tentativas erradas e nunca diz qual dado errou. O prompt só cuida do que depende do modelo (tom, escopo, não prometer desconto).
- **Busca nas políticas por BM25, sem embeddings.** São 25 seções curtas, o plano gratuito do OpenRouter não tem endpoint estável de embeddings, e BM25 é determinístico, offline e testável. A tool devolve seção e página como fonte e `NOT_IN_POLICIES` quando não há resposta, para o agente não chutar.
- **Contradições do manual resolvidas em código** (`knowledge/errata.py`), anexadas à seção onde aparecem, para o modelo nunca precisar decidir qual fonte vale.
- **Provedor atrás de uma interface.** Trocar o OpenRouter por outro provedor é escrever uma classe `LLMClient` e uma linha em `build_llm`. O modelo nunca fica fixo no código.
- **Resiliência com modelos gratuitos.** Retry com backoff exponencial e `Retry-After` para 429 e 5xx. Se um modelo esgota as tentativas, vai para o próximo da lista. Modelo que responde 400/404 sai da lista na sessão, e modelo com limite de taxa descansa 60 s. Se o LLM cair de vez, o cliente recebe uma desculpa com o telefone da loja, sem erro técnico.
- **Data de "hoje" injetável** (`STORE_TODAY` ou `--today`), usada nas ferramentas e no prompt. Os exemplos fixam a data para serem reproduzíveis.

### Guardrails

- Recusa o que está fora do escopo da loja (exemplo 05).
- A loja só vende instrumentos: pedido de palheta, corda avulsa, capa etc. é recusado na ferramenta de busca (`ACCESSORY_NOT_SOLD`) e na persona.
- Não inventa dado: toda informação factual vem de ferramenta; sem dado, oferece o contato da loja.
- Identidade verificada (e-mail ou telefone, com número do pedido quando o contato é ambíguo) antes de qualquer informação de pedido ou devolução.
- Só fala em promoção quando o produto tem promoção no dado (`promotion` não nulo).
- Resultado de busca truncado traz uma `note` com o total real, para o agente não confundir o limite da busca com a quantidade de produtos.

## Estrutura

```
data/        CSVs e manual de políticas (PDF)
examples/    conversas reais do agente
prompts/     persona do agente
scripts/     list_free_models.py, generate_examples.py
src/emporio/ código (camadas na tabela acima)
tests/       testes (pytest)
```
