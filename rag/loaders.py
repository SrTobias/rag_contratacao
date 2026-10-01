"""Extração de texto de PDF, DOCX, TXT e MD."""
from __future__ import annotations

import io
import re
from collections import Counter
from pathlib import Path
from typing import List

EXTENSOES_SUPORTADAS = (".pdf", ".docx", ".txt", ".md")

_PAGINA_RE = re.compile(r"^\s*(P[áa]g(ina)?\.?\s*)?\d+(\s*(de|/)\s*\d+)?\s*$", re.I)


def load_path(path: Path) -> str:
    return load_bytes(path.name, path.read_bytes())


def load_bytes(filename: str, data: bytes) -> str:
    ext = Path(filename).suffix.lower()
    if ext == ".pdf":
        text = _load_pdf(data)
    elif ext == ".docx":
        text = _load_docx(data)
    elif ext in (".txt", ".md"):
        text = data.decode("utf-8", errors="replace")
    else:
        raise ValueError(f"Formato não suportado: {ext} (suportados: {', '.join(EXTENSOES_SUPORTADAS)})")
    return normalizar(text)


def normalizar(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x0c", "\n").replace("\xa0", " ")
    linhas = [re.sub(r"[ \t]+", " ", linha).strip() for linha in text.split("\n")]
    linhas = [linha for linha in linhas if not _PAGINA_RE.match(linha) or not linha]
    text = "\n".join(linhas)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _load_pdf(data: bytes) -> str:
    from pypdf import PdfReader

    paginas = [p.extract_text() or "" for p in PdfReader(io.BytesIO(data)).pages]
    return "\n\n".join(_remover_cabecalhos_rodapes(paginas))


_ARESTAS = 3  # linhas no topo e no fundo de cada página onde se procuram cabeçalhos/rodapés


def _chave_rodape(linha: str) -> str:
    """Normaliza números para que 'Pág. 31 de 235' e 'Pág. 32 de 235' contem como a mesma linha."""
    return re.sub(r"\d+", "#", re.sub(r"\s+", " ", linha.replace("\xa0", " ")).strip())


def _remover_cabecalhos_rodapes(paginas: List[str]) -> List[str]:
    """Remove linhas curtas que se repetem no topo/fundo da maioria das páginas."""
    if len(paginas) < 4:
        return paginas
    contagem: Counter = Counter()
    for pagina in paginas:
        linhas = [l for l in pagina.split("\n") if l.strip()]
        for linha in set(linhas[:_ARESTAS] + linhas[-_ARESTAS:]):
            if len(linha.strip()) < 120:
                contagem[_chave_rodape(linha)] += 1
    repetidas = {l for l, n in contagem.items() if n >= len(paginas) * 0.5}
    if not repetidas:
        return paginas

    def limpar(pagina: str) -> str:
        linhas = pagina.split("\n")
        idx = [i for i, l in enumerate(linhas) if l.strip()]
        arestas = set(idx[:_ARESTAS] + idx[-_ARESTAS:])
        return "\n".join(l for i, l in enumerate(linhas) if not (i in arestas and _chave_rodape(l) in repetidas))

    return [limpar(p) for p in paginas]


def _load_docx(data: bytes) -> str:
    """Lê parágrafos e tabelas pela ordem em que aparecem no documento."""
    from docx import Document
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    doc = Document(io.BytesIO(data))
    partes: List[str] = []
    for el in doc.element.body.iterchildren():
        tag = el.tag.rsplit("}", 1)[-1]
        if tag == "p":
            partes.append(Paragraph(el, doc).text)
        elif tag == "tbl":
            for row in Table(el, doc).rows:
                celulas = []
                for cell in row.cells:
                    t = cell.text.strip()
                    if t and (not celulas or celulas[-1] != t):  # células unidas repetem o texto
                        celulas.append(t)
                if celulas:
                    partes.append(" | ".join(celulas))
            partes.append("")
    return "\n".join(partes)
