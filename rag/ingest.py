"""Ingestão de documentos no índice.

Exemplos (linha de comandos):
    python -m rag.ingest data/legislacao/CCP.pdf --fonte legislacao --diploma "CCP"
    python -m rag.ingest data/pecas/cadernos/ --fonte peca --tipo-peca caderno_encargos \\
        --tipo-procedimento concurso_publico --tipo-contrato aquisicao_servicos
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Dict, List, Optional

from .chunking import Chunk, chunk_documento, chunk_legislacao, contar_artigos
from .config import Settings
from .embeddings import Embedder
from .loaders import EXTENSOES_SUPORTADAS, load_bytes
from .store import Store
from .taxonomy import FONTES, TIPOS_CONTRATO, TIPOS_PROCEDIMENTO


def criar_chunks(filename: str, data: bytes, meta: Dict[str, str]) -> List[Chunk]:
    text = load_bytes(filename, data)
    titulo = meta.get("titulo_doc") or Path(filename).stem
    base = {**meta, "titulo_doc": titulo}
    if meta.get("fonte") == "legislacao" and contar_artigos(text) >= 3:
        return chunk_legislacao(text, meta.get("diploma") or titulo, base)
    return chunk_documento(text, titulo, base)


def ingerir(store: Store, filename: str, data: bytes, meta: Dict[str, str], source: Optional[str] = None) -> int:
    """Indexa um ficheiro. `source` identifica o documento (re-ingerir substitui a versão anterior)."""
    chunks = criar_chunks(filename, data, meta)
    return store.adicionar(chunks, source or filename)


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Indexar documentos para o RAG de contratação pública.")
    p.add_argument("caminho", type=Path, help="Ficheiro ou pasta")
    p.add_argument("--fonte", required=True, choices=list(FONTES))
    p.add_argument("--diploma", help="Designação do diploma (legislação), ex.: CCP")
    p.add_argument("--tipo-peca", help="Tipo de peça (id do template, ex.: caderno_encargos)")
    p.add_argument("--tipo-procedimento", choices=list(TIPOS_PROCEDIMENTO))
    p.add_argument("--tipo-contrato", choices=list(TIPOS_CONTRATO))
    p.add_argument("--ano")
    args = p.parse_args(argv)

    if args.caminho.is_dir():
        ficheiros = sorted(f for f in args.caminho.rglob("*") if f.suffix.lower() in EXTENSOES_SUPORTADAS)
    else:
        ficheiros = [args.caminho]
    if not ficheiros:
        print("Nenhum ficheiro suportado encontrado.", file=sys.stderr)
        return 1

    settings = Settings.from_env()
    store = Store(settings.index_dir, Embedder(settings))
    meta = {
        "fonte": args.fonte,
        "diploma": args.diploma,
        "tipo_peca": args.tipo_peca,
        "tipo_procedimento": args.tipo_procedimento,
        "tipo_contrato": args.tipo_contrato,
        "ano": args.ano,
    }
    meta = {k: v for k, v in meta.items() if v}
    for f in ficheiros:
        try:
            n = ingerir(store, f.name, f.read_bytes(), meta)
            print(f"[ok] {f.name}: {n} excertos")
        except Exception as e:  # noqa: BLE001 - continuar com os restantes ficheiros
            print(f"[erro] {f.name}: {e}", file=sys.stderr)
    print(f"Total no índice: {store.contar()} excertos")
    return 0


if __name__ == "__main__":
    sys.exit(main())
