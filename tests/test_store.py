import hashlib

import pytest

pytest.importorskip("chromadb")

from rag.chunking import chunk_legislacao, chunk_documento  # noqa: E402
from rag.store import Store, tokenizar  # noqa: E402
from tests.test_chunking import CCP, PECA  # noqa: E402


class FakeEmbedder:
    """Embedding determinístico por hashing de palavras (sem modelo)."""

    def _vec(self, text):
        v = [0.0] * 64
        for t in tokenizar(text):
            v[int(hashlib.md5(t.encode()).hexdigest(), 16) % 64] += 1.0
        n = sum(x * x for x in v) ** 0.5 or 1.0
        return [x / n for x in v]

    def embed_documents(self, texts):
        return [self._vec(t) for t in texts]

    def embed_query(self, text):
        return self._vec(text)


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path, FakeEmbedder())
    s.adicionar(chunk_legislacao(CCP, "CCP", {"fonte": "legislacao"}), "ccp.pdf")
    s.adicionar(
        chunk_documento(PECA, "CE limpeza", {"fonte": "peca", "tipo_peca": "caderno_encargos", "tipo_contrato": "aquisicao_servicos"}),
        "ce.docx",
    )
    return s


def test_obter_artigos_diretamente(store):
    hits = store.obter_artigos(["67", "46-A"], {"diploma": "CCP"})
    assert [h.metadata["artigo"] for h in hits] == ["67", "46-A"]
    assert store.obter_artigos(["67"], {"diploma": "Outro"}) == []


def test_pesquisa_hibrida_com_filtros(store):
    hits = store.pesquisar("júri do procedimento", k=3, filtros={"fonte": ["legislacao", "orientacao"]})
    assert hits and hits[0].metadata["artigo"] == "67"
    assert all(h.metadata["fonte"] == "legislacao" for h in hits)
    ex = store.pesquisar("prazo do contrato", k=3, filtros={"fonte": "peca", "tipo_peca": "caderno_encargos"})
    assert ex and all(h.metadata["source"] == "ce.docx" for h in ex)


def test_reingerir_substitui_e_remover(store):
    antes = store.contar()
    store.adicionar(chunk_legislacao(CCP, "CCP", {"fonte": "legislacao"}), "ccp.pdf")
    assert store.contar() == antes
    store.remover("ce.docx")
    assert {f["source"] for f in store.listar_fontes()} == {"ccp.pdf"}
    assert store.pesquisar("limpeza", k=3, filtros={"fonte": "peca"}) == []
