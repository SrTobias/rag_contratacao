"""Recolha de contexto e redação de peças secção a secção."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterator, List, Tuple

from .config import Settings
from .llm import LLM, Messages
from .store import Hit, Store
from .taxonomy import CAMPOS_COMUNS, TIPOS_CONTRATO, TIPOS_PROCEDIMENTO
from .templates import Secao, Template, rotulo

# Diploma a que se referem os números de artigo indicados em `base_legal` nos templates.
# O CCP deve ser indexado com --diploma CCP.
DIPLOMA_BASE = "CCP"

SYSTEM_REDACAO = """És um jurista especializado em contratação pública portuguesa, com profundo conhecimento do \
Código dos Contratos Públicos (CCP) e legislação conexa. Redige peças de procedimento em português europeu, \
em linguagem jurídico-administrativa formal, clara e rigorosa.

Regras obrigatórias:
1. Fundamenta-te apenas nas disposições legais que constam do CONTEXTO LEGAL. Quando citares, usa a forma \
"artigo X.º do CCP" (ou do diploma indicado). Nunca inventes números de artigos nem conteúdos legais; se \
precisares de uma referência que não está no contexto, escreve [VERIFICAR: descrição da referência em falta].
2. Os EXEMPLOS DE PEÇAS ANTERIORES servem apenas de referência de estrutura, estilo e boas práticas. Nunca \
copies dados concretos de outros procedimentos (entidades, valores, datas, nomes, prazos).
3. Usa os DADOS DO PROCEDIMENTO fornecidos. Qualquer informação necessária que não tenha sido fornecida deve \
ficar assinalada como [PREENCHER: descrição].
4. Redige apenas o corpo da secção pedida, sem repetir o título e sem comentários, notas ou explicações fora \
do texto da peça.
5. Quando a secção tiver vários números, numera-os no formato "1 - ", "2 - ", ...; alíneas no formato "a) ", "b) ".
6. Podes fazer remissões para outras secções da mesma peça usando a numeração indicada no ÍNDICE DA PEÇA."""

SYSTEM_CONSULTA = """És um assistente jurídico especializado em contratação pública portuguesa. Responde em \
português europeu, de forma rigorosa e concisa, com base exclusivamente no CONTEXTO fornecido. Cita as fontes \
com os identificadores entre parênteses retos (ex.: [L1], [E2]) e indica os artigos aplicáveis. Se o contexto \
não for suficiente para responder com segurança, di-lo claramente em vez de especular."""


@dataclass
class Contexto:
    legislacao: List[Hit]
    exemplos: List[Hit]

    def fontes(self) -> List[str]:
        return [f"[L{i}] {h.referencia}" for i, h in enumerate(self.legislacao, 1)] + [
            f"[E{i}] {h.referencia}" for i, h in enumerate(self.exemplos, 1)
        ]


def _rotulos_campos(template: Template) -> Dict[str, str]:
    return {c["id"]: c["rotulo"] for c in CAMPOS_COMUNS + template.campos_extra}


def formatar_dados(template: Template, dados: Dict[str, str]) -> str:
    rotulos = _rotulos_campos(template)
    linhas = [f"- {rotulos.get(k, k)}: {v.strip()}" for k, v in dados.items() if v and v.strip()]
    return "\n".join(linhas) or "(nenhum dado fornecido)"


def recolher_contexto(
    store: Store,
    settings: Settings,
    template: Template,
    secao: Secao,
    tipo_procedimento: str,
    tipo_contrato: str,
    dados: Dict[str, str],
) -> Contexto:
    proc = TIPOS_PROCEDIMENTO.get(tipo_procedimento, tipo_procedimento)
    contrato = TIPOS_CONTRATO.get(tipo_contrato, tipo_contrato)
    query = " ".join(
        p for p in [secao.titulo, secao.pesquisa, template.nome, proc, contrato, dados.get("objeto", "")[:300]] if p
    )

    # 1) Artigos indicados no template, obtidos diretamente; 2) pesquisa híbrida na legislação/orientações.
    legislacao = store.obter_artigos(secao.base_legal, {"diploma": DIPLOMA_BASE})
    vistos = {h.id for h in legislacao}
    for h in store.pesquisar(query, k=settings.top_k_legislacao, filtros={"fonte": ["legislacao", "orientacao"]}):
        if h.id not in vistos:
            legislacao.append(h)
            vistos.add(h.id)

    # Exemplos: mesma peça e tipo de contrato; se houver poucos, alarga a todos os tipos de contrato.
    exemplos: List[Hit] = []
    if template.id != "peca_livre":
        filtros = {"fonte": "peca", "tipo_peca": template.id, "tipo_contrato": tipo_contrato}
        exemplos = store.pesquisar(query, k=settings.top_k_exemplos, filtros=filtros)
        if len(exemplos) < settings.top_k_exemplos:
            ids = {h.id for h in exemplos}
            extra = store.pesquisar(query, k=settings.top_k_exemplos, filtros={"fonte": "peca", "tipo_peca": template.id})
            exemplos += [h for h in extra if h.id not in ids][: settings.top_k_exemplos - len(exemplos)]
    else:
        exemplos = store.pesquisar(query, k=settings.top_k_exemplos, filtros={"fonte": "peca"})

    return _limitar(Contexto(legislacao, exemplos), settings.max_context_chars)


def _limitar(ctx: Contexto, max_chars: int) -> Contexto:
    """Corta o contexto ao orçamento de caracteres, dando prioridade à legislação."""
    total = 0
    leg, ex = [], []
    for h in ctx.legislacao:
        if total + len(h.text) > max_chars * 0.65 and leg:
            break
        leg.append(h)
        total += len(h.text)
    for h in ctx.exemplos:
        if total + len(h.text) > max_chars and ex:
            break
        ex.append(h)
        total += len(h.text)
    return Contexto(leg, ex)


def _bloco_contexto(ctx: Contexto) -> str:
    leg = "\n\n".join(f"[L{i}] {h.text}" for i, h in enumerate(ctx.legislacao, 1)) or "(sem resultados)"
    ex = "\n\n".join(f"[E{i}] {h.text}" for i, h in enumerate(ctx.exemplos, 1)) or "(sem exemplos disponíveis)"
    return f"CONTEXTO LEGAL:\n{leg}\n\nEXEMPLOS DE PEÇAS ANTERIORES:\n{ex}"


def mensagens_secao(
    template: Template,
    secao: Secao,
    numero: int,
    indice: List[Tuple[int, Secao]],
    tipo_procedimento: str,
    tipo_contrato: str,
    dados: Dict[str, str],
    ctx: Contexto,
) -> Messages:
    indice_txt = "\n".join(f"{rotulo(template.numeracao, n)} {s.titulo}" for n, s in indice)
    partes = [
        f"TIPO DE PEÇA: {template.nome}",
        f"PROCEDIMENTO: {TIPOS_PROCEDIMENTO.get(tipo_procedimento, tipo_procedimento)}",
        f"TIPO DE CONTRATO: {TIPOS_CONTRATO.get(tipo_contrato, tipo_contrato)}",
        f"\nDADOS DO PROCEDIMENTO:\n{formatar_dados(template, dados)}",
        f"\nÍNDICE DA PEÇA:\n{indice_txt}",
    ]
    if template.instrucoes_gerais:
        partes.append(f"\nINSTRUÇÕES GERAIS DA PEÇA:\n{template.instrucoes_gerais.strip()}")
    partes += [
        f"\nSECÇÃO A REDIGIR: {rotulo(template.numeracao, numero)} {secao.titulo}",
        f"INSTRUÇÕES DA SECÇÃO:\n{secao.instrucoes.strip() or 'Redige o conteúdo adequado a esta secção.'}",
        f"\n{_bloco_contexto(ctx)}",
        f"\nRedige agora apenas o corpo da secção \"{secao.titulo}\".",
    ]
    return [{"role": "system", "content": SYSTEM_REDACAO}, {"role": "user", "content": "\n".join(partes)}]


def redigir_secao(
    llm: LLM,
    store: Store,
    settings: Settings,
    template: Template,
    secao: Secao,
    numero: int,
    indice: List[Tuple[int, Secao]],
    tipo_procedimento: str,
    tipo_contrato: str,
    dados: Dict[str, str],
) -> Tuple[Iterator[str], Contexto]:
    ctx = recolher_contexto(store, settings, template, secao, tipo_procedimento, tipo_contrato, dados)
    msgs = mensagens_secao(template, secao, numero, indice, tipo_procedimento, tipo_contrato, dados, ctx)
    return llm.stream(msgs), ctx


def consultar(llm: LLM, store: Store, pergunta: str, historico: Messages, k: int = 8) -> Tuple[Iterator[str], Contexto]:
    hits = store.pesquisar(pergunta, k=k)
    ctx = Contexto(
        [h for h in hits if h.metadata.get("fonte") != "peca"],
        [h for h in hits if h.metadata.get("fonte") == "peca"],
    )
    msgs: Messages = [{"role": "system", "content": SYSTEM_CONSULTA}]
    msgs += historico[-6:]
    msgs.append({"role": "user", "content": f"{_bloco_contexto(ctx)}\n\nPERGUNTA: {pergunta}"})
    return llm.stream(msgs), ctx
