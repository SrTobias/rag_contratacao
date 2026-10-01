"""Carregamento dos templates de peças (ficheiros YAML em templates/)."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

import yaml


@dataclass
class Secao:
    id: str
    titulo: str
    instrucoes: str = ""
    pesquisa: str = ""
    base_legal: List[str] = field(default_factory=list)
    condicao: Dict[str, List[str]] = field(default_factory=dict)
    opcional: bool = False
    parte: str = ""

    def aplicavel(self, tipo_procedimento: str, tipo_contrato: str) -> bool:
        valores = {"tipo_procedimento": tipo_procedimento, "tipo_contrato": tipo_contrato}
        return all(valores.get(k) in v for k, v in self.condicao.items())


@dataclass
class Template:
    id: str
    nome: str
    descricao: str = ""
    numeracao: str = "seccao"  # artigo | clausula | seccao
    procedimentos: List[str] = field(default_factory=list)  # vazio = todos
    campos_extra: List[Dict[str, str]] = field(default_factory=list)
    instrucoes_gerais: str = ""
    secoes: List[Secao] = field(default_factory=list)

    def secoes_aplicaveis(self, tipo_procedimento: str, tipo_contrato: str) -> List[Secao]:
        return [s for s in self.secoes if s.aplicavel(tipo_procedimento, tipo_contrato)]


def rotulo(numeracao: str, n: int) -> str:
    if numeracao == "artigo":
        return f"Artigo {n}.º"
    if numeracao == "clausula":
        return f"Cláusula {n}.ª"
    return f"{n}."


def carregar_templates(pasta: Path) -> Dict[str, Template]:
    templates: Dict[str, Template] = {}
    for f in sorted(pasta.glob("*.yaml")):
        raw = yaml.safe_load(f.read_text(encoding="utf-8"))
        secoes = [Secao(**{**s, "base_legal": [str(a) for a in s.get("base_legal", [])]}) for s in raw.pop("secoes", [])]
        t = Template(**raw, secoes=secoes)
        templates[t.id] = t
    return templates


def template_personalizado(nome: str, titulos: List[str], numeracao: str = "seccao") -> Template:
    """Peça livre: o utilizador indica o nome e os títulos das secções."""
    secoes = [Secao(id=f"s{i}", titulo=t.strip()) for i, t in enumerate(titulos) if t.strip()]
    return Template(id="peca_livre", nome=nome or "Peça", numeracao=numeracao, secoes=secoes)
