"""Divisão de documentos em excertos.

- Legislação: um excerto por artigo (artigos longos divididos pelos seus números),
  com o diploma, número, epígrafe e localização sistemática nos metadados.
- Peças e orientações: divisão por cláusulas/artigos/títulos numerados, com
  agregação de secções curtas e divisão de secções longas.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

MAX_CHARS = 2500
MIN_CHARS = 300
OVERLAP = 200


@dataclass
class Chunk:
    text: str
    metadata: Dict[str, str] = field(default_factory=dict)


# --------------------------------------------------------------------------- legislação

_ARTIGO_RE = re.compile(r"^Artigo\s+(\d+)\s*\.?\s*[º°o]?\s*(?:-\s*([A-Z]))?\s*$")
_ESTRUTURA_RE = re.compile(
    r"^(PARTE|T[ÍI]TULO|CAP[ÍI]TULO|SEC[ÇC][ÃA]O|SUBSEC[ÇC][ÃA]O)\s+([IVXLCDM]+|\d+|[ÚU]NIC[OA])\b",
    re.I,
)
_NIVEIS = ["PARTE", "TITULO", "CAPITULO", "SECCAO", "SUBSECCAO"]
_NUMERO_RE = re.compile(r"^\d+\s*[-–—]\s")


def _nivel(palavra: str) -> str:
    return (
        palavra.upper()
        .replace("Í", "I")
        .replace("Ç", "C")
        .replace("Ã", "A")
    )


def normalizar_artigo(num: str, letra: Optional[str] = None) -> str:
    """'46', 'A' -> '46-A' (forma usada nos metadados e nos templates)."""
    return f"{int(num)}-{letra.upper()}" if letra else str(int(num))


def rotulo_artigo(artigo: str) -> str:
    """'46-A' -> '46.º-A'."""
    num, _, letra = artigo.partition("-")
    return f"{num}.º" + (f"-{letra}" if letra else "")


def _proxima_linha(linhas: List[str], i: int) -> Tuple[Optional[str], int]:
    j = i + 1
    while j < len(linhas) and not linhas[j].strip():
        j += 1
    return (linhas[j].strip(), j) if j < len(linhas) else (None, j)


def chunk_legislacao(text: str, diploma: str, base_meta: Optional[Dict[str, str]] = None) -> List[Chunk]:
    base_meta = dict(base_meta or {})
    linhas = text.split("\n")
    estrutura: Dict[str, str] = {}
    artigos: List[Tuple[str, str, str, List[str]]] = []  # (artigo, epígrafe, estrutura, corpo)
    preambulo: List[str] = []
    atual: Optional[Tuple[str, str, str, List[str]]] = None

    i = 0
    while i < len(linhas):
        linha = linhas[i].strip()
        m_art = _ARTIGO_RE.match(linha)
        m_est = _ESTRUTURA_RE.match(linha) if not m_art else None
        if m_art:
            epigrafe, j = _proxima_linha(linhas, i)
            if epigrafe and len(epigrafe) < 160 and not _NUMERO_RE.match(epigrafe) and not _ARTIGO_RE.match(epigrafe):
                i = j
            else:
                epigrafe = ""
            atual = (
                normalizar_artigo(m_art.group(1), m_art.group(2)),
                epigrafe,
                " > ".join(v for v in estrutura.values() if v),
                [],
            )
            artigos.append(atual)
        elif m_est:
            nivel = _nivel(m_est.group(1))
            nome, j = _proxima_linha(linhas, i)
            designacao = linha
            if nome and len(nome) < 160 and not _ARTIGO_RE.match(nome) and not _ESTRUTURA_RE.match(nome):
                designacao = f"{linha} — {nome}"
                i = j
            # Ao mudar de nível, os níveis inferiores deixam de se aplicar.
            idx = _NIVEIS.index(nivel) if nivel in _NIVEIS else len(_NIVEIS)
            estrutura = {k: v for k, v in estrutura.items() if k in _NIVEIS and _NIVEIS.index(k) < idx}
            estrutura[nivel] = designacao
        elif atual is not None:
            atual[3].append(linhas[i])
        else:
            preambulo.append(linhas[i])
        i += 1

    chunks: List[Chunk] = []
    texto_preambulo = "\n".join(preambulo).strip()
    if texto_preambulo:
        meta = {**base_meta, "diploma": diploma, "artigo": "", "seccao": "Preâmbulo"}
        for parte in _dividir_longo(texto_preambulo):
            chunks.append(Chunk(f"{diploma} — Preâmbulo\n\n{parte}", dict(meta)))

    for artigo, epigrafe, local, corpo in artigos:
        corpo_txt = "\n".join(corpo).strip()
        if not corpo_txt:
            continue
        cabecalho = f"{diploma} — Artigo {rotulo_artigo(artigo)}" + (f" ({epigrafe})" if epigrafe else "")
        meta = {
            **base_meta,
            "diploma": diploma,
            "artigo": artigo,
            "epigrafe": epigrafe,
            "estrutura": local,
            "seccao": f"Artigo {rotulo_artigo(artigo)}" + (f" — {epigrafe}" if epigrafe else ""),
        }
        partes = _dividir_por_numeros(corpo_txt)
        for n, parte in enumerate(partes):
            sufixo = " (cont.)" if n else ""
            chunks.append(Chunk(f"{cabecalho}{sufixo}\n{local}\n\n{parte}".replace("\n\n\n", "\n\n"), dict(meta)))
    return chunks


def contar_artigos(text: str) -> int:
    return sum(1 for l in text.split("\n") if _ARTIGO_RE.match(l.strip()))


def _dividir_por_numeros(text: str, max_chars: int = MAX_CHARS) -> List[str]:
    """Divide um artigo longo pelos seus números ('1 - ...', '2 - ...')."""
    if len(text) <= max_chars:
        return [text]
    blocos = [b.strip() for b in re.split(r"\n(?=\d+\s*[-–—]\s)", text) if b.strip()]
    partes: List[str] = []
    atual = ""
    for bloco in blocos:
        if len(bloco) > max_chars:
            if atual:
                partes.append(atual)
                atual = ""
            partes.extend(_dividir_longo(bloco, max_chars))
        elif len(atual) + len(bloco) + 1 > max_chars:
            partes.append(atual)
            atual = bloco
        else:
            atual = f"{atual}\n{bloco}" if atual else bloco
    if atual:
        partes.append(atual)
    return partes


# --------------------------------------------------------------------------- peças / orientações

_CLAUSULA_RE = re.compile(
    r"^(Cl[áa]usula|Artigo|Art\.)\s+(\d+)\s*\.?\s*[ªº°ao]?\s*(?:-\s*[A-Z]\b)?\s*(?:[-–—:.]\s*(.{2,120}))?$",
    re.I,
)
_NUM_TITULO_RE = re.compile(r"^(\d{1,2}(?:\.\d{1,2}){0,2})\.?\s+([A-ZÁÂÃÀÉÊÍÓÔÕÚÇ].{2,100})$")
_PARTE_RE = re.compile(r"^(PARTE|ANEXO|CAP[ÍI]TULO)\s+([IVXLC]+|\d+|[ÚU]NIC[OA])\b.{0,100}$", re.I)


def _e_titulo(linha: str, seguinte: Optional[str]) -> Tuple[Optional[str], bool]:
    """Devolve (título, consumiu_linha_seguinte) se a linha for um título de secção."""
    if not linha or len(linha) > 140:
        return None, False
    m = _CLAUSULA_RE.match(linha)
    if m:
        if m.group(3):
            return linha, False
        if seguinte and len(seguinte) < 120 and not seguinte.endswith((".", ";", ",")) and not _CLAUSULA_RE.match(seguinte):
            return f"{linha} — {seguinte}", True
        return linha, False
    if _PARTE_RE.match(linha):
        return linha, False
    m = _NUM_TITULO_RE.match(linha)
    if m and not linha.endswith((".", ";", ":", ",")) and len(linha.split()) <= 14:
        return linha, False
    letras = [c for c in linha if c.isalpha()]
    if len(letras) >= 4 and linha.isupper() and not linha.endswith((".", ";", ",")):
        return linha, False
    return None, False


def _seccoes(text: str) -> List[Tuple[str, str]]:
    linhas = [l.strip() for l in text.split("\n")]
    seccoes: List[Tuple[str, List[str]]] = [("", [])]
    i = 0
    while i < len(linhas):
        linha = linhas[i]
        seguinte, j = _proxima_linha(linhas, i)
        titulo, consumiu = _e_titulo(linha, seguinte)
        if titulo:
            seccoes.append((titulo, []))
            i = j + 1 if consumiu else i + 1
            continue
        seccoes[-1][1].append(linha)
        i += 1
    return [(t, "\n".join(c).strip()) for t, c in seccoes if t or "\n".join(c).strip()]


def chunk_documento(text: str, titulo_doc: str, base_meta: Optional[Dict[str, str]] = None) -> List[Chunk]:
    base_meta = dict(base_meta or {})
    chunks: List[Chunk] = []
    buffer_titulos: List[str] = []
    buffer_txt = ""

    def emitir(titulos: List[str], corpo: str) -> None:
        titulo = " / ".join(t for t in titulos if t)
        for n, parte in enumerate(_dividir_longo(corpo)):
            cab = f"[{titulo_doc}]" + (f" {titulo}" if titulo else "") + (" (cont.)" if n else "")
            chunks.append(Chunk(f"{cab}\n\n{parte}", {**base_meta, "seccao": titulo}))

    # Secções curtas são agregadas à seguinte, mantendo os títulos de todas.
    for titulo, corpo in _seccoes(text):
        bloco = f"{titulo}\n{corpo}".strip() if titulo else corpo
        if buffer_txt and len(buffer_txt) >= MIN_CHARS:
            emitir(buffer_titulos, buffer_txt)
            buffer_titulos, buffer_txt = [], ""
        buffer_titulos.append(titulo)
        buffer_txt = f"{buffer_txt}\n\n{bloco}" if buffer_txt else bloco
    if buffer_txt:
        emitir(buffer_titulos, buffer_txt)
    return chunks


# --------------------------------------------------------------------------- utilitários

def _dividir_longo(text: str, max_chars: int = MAX_CHARS, overlap: int = OVERLAP) -> List[str]:
    """Divide por parágrafos/linhas/frases, com sobreposição entre partes."""
    if len(text) <= max_chars:
        return [text]
    unidades: List[str] = []
    for par in re.split(r"\n\s*\n", text):
        if len(par) <= max_chars:
            unidades.append(par)
            continue
        for linha in par.split("\n"):
            if len(linha) <= max_chars:
                unidades.append(linha)
            else:
                unidades.extend(re.split(r"(?<=[.;])\s+", linha))

    partes: List[str] = []
    atual = ""
    for u in unidades:
        if len(u) > max_chars:  # frase gigante: corte duro
            u_partes = [u[k : k + max_chars] for k in range(0, len(u), max_chars - overlap)]
        else:
            u_partes = [u]
        for up in u_partes:
            if atual and len(atual) + len(up) + 2 > max_chars:
                partes.append(atual)
                cauda = atual[-overlap:]
                cauda = cauda[cauda.find(" ") + 1 :] if " " in cauda else cauda
                atual = f"…{cauda}\n{up}"
            else:
                atual = f"{atual}\n{up}" if atual else up
    if atual:
        partes.append(atual)
    return partes
