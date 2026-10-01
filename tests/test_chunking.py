from rag.chunking import MAX_CHARS, chunk_documento, chunk_legislacao, contar_artigos, rotulo_artigo
from rag.loaders import normalizar

CCP = """Decreto-Lei n.º 18/2008
Aprova o Código dos Contratos Públicos

PARTE II
Contratação pública
TÍTULO I
Tipos e escolha de procedimentos
CAPÍTULO II
Peças do procedimento

Artigo 40.º
Tipos e elaboração das peças dos procedimentos
1 - As peças dos procedimentos de formação de contratos são as seguintes:
a) No ajuste direto, o convite à apresentação das propostas e o caderno de encargos;
2 - As peças referidas no número anterior são aprovadas pelo órgão competente.

Artigo 46.º-A
Adjudicação por lotes
1 - A entidade adjudicante pode adjudicar por lotes.

CAPÍTULO III
Júri do procedimento

Artigo 67.º
Designação e funcionamento do júri
1 - Os procedimentos são conduzidos por um júri.
"""


def test_legislacao_um_chunk_por_artigo():
    chunks = chunk_legislacao(normalizar(CCP), "CCP", {"fonte": "legislacao"})
    artigos = [c.metadata["artigo"] for c in chunks if c.metadata["artigo"]]
    assert artigos == ["40", "46-A", "67"]
    c40 = next(c for c in chunks if c.metadata["artigo"] == "40")
    assert c40.metadata["epigrafe"] == "Tipos e elaboração das peças dos procedimentos"
    assert "CAPÍTULO II — Peças do procedimento" in c40.metadata["estrutura"]
    assert "PARTE II — Contratação pública" in c40.metadata["estrutura"]
    assert c40.text.startswith("CCP — Artigo 40.º (Tipos e elaboração")
    c67 = next(c for c in chunks if c.metadata["artigo"] == "67")
    assert "CAPÍTULO III — Júri do procedimento" in c67.metadata["estrutura"]
    assert "CAPÍTULO II —" not in c67.metadata["estrutura"]


def test_legislacao_preambulo_e_contagem():
    chunks = chunk_legislacao(normalizar(CCP), "CCP")
    assert chunks[0].metadata["seccao"] == "Preâmbulo"
    assert contar_artigos(CCP) == 3
    assert rotulo_artigo("46-A") == "46.º-A"


def test_artigo_longo_dividido_por_numeros():
    numeros = "\n".join(f"{i} - " + "texto do número " * 40 for i in range(1, 15))
    chunks = chunk_legislacao(f"Artigo 70.º\nAnálise das propostas\n{numeros}", "CCP")
    assert len(chunks) > 1
    assert all(len(c.text) <= MAX_CHARS + 200 for c in chunks)
    assert all(c.metadata["artigo"] == "70" for c in chunks)
    assert "(cont.)" in chunks[1].text


PECA = """CADERNO DE ENCARGOS
Aquisição de serviços de limpeza

Cláusula 1.ª
Objeto
O presente caderno de encargos compreende as cláusulas a incluir no contrato a celebrar na sequência do procedimento.
""" + "Texto adicional do objeto. " * 20 + """

Cláusula 2.ª – Prazo
O contrato mantém-se em vigor pelo prazo de 12 meses.
""" + "Mais texto sobre o prazo. " * 20


def test_peca_dividida_por_clausulas():
    chunks = chunk_documento(normalizar(PECA), "CE limpeza", {"fonte": "peca"})
    seccoes = [c.metadata["seccao"] for c in chunks]
    assert seccoes == ["CADERNO DE ENCARGOS / Cláusula 1.ª — Objeto", "Cláusula 2.ª – Prazo"]
    assert all(c.metadata["fonte"] == "peca" for c in chunks)
    assert all(c.text.startswith("[CE limpeza]") for c in chunks)
