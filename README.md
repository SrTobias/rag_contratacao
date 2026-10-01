# RAG — Peças de Procedimento de Contratação Pública

Aplicação web (Streamlit) que gera rascunhos de peças de procedimento com base no Código dos Contratos
Públicos (CCP), em orientações e em peças anteriores da organização. Tudo corre localmente no servidor
onde a aplicação está instalada.

> O texto gerado é um **rascunho** que exige sempre revisão jurídica. Os marcadores `[PREENCHER: ...]` e
> `[VERIFICAR: ...]` assinalam informação em falta ou referências legais a confirmar.

## Funcionalidades

- **Gerar peça:** decisão de contratar, programa do procedimento, convite, caderno de encargos,
  relatórios preliminar e final, minuta do contrato, ou peça personalizada. A peça é gerada secção a
  secção (cláusulas e artigos), adaptada ao procedimento e ao tipo de contrato, pode ser editada e
  regenerada por secção e é exportada para Word com um anexo de rastreabilidade das fontes.
- **Consultar:** perguntas sobre a base documental, com indicação das fontes.
- **Base documental:** carregamento de PDF/DOCX/TXT/MD com metadados, listagem e remoção.

## Arquitetura

```
Documentos ──► extração de texto ──► divisão em excertos ──► embeddings (bge-m3, local) ──► Chroma (local)
                                      · CCP: 1 excerto por artigo                           + índice BM25
                                      · peças: por cláusula
Pedido ──► por secção: artigos do template (diretos) + pesquisa híbrida (legislação) + exemplos (peças)
       ──► LLM (Ollama/vLLM interno ou Azure OpenAI UE) ──► revisão ──► .docx
```

| Pasta | Conteúdo |
|---|---|
| `rag/` | Núcleo: extração (`loaders`), divisão (`chunking`), índice (`store`), geração (`generation`), exportação (`export_docx`) |
| `app/streamlit_app.py` | Interface web |
| `templates/*.yaml` | Estrutura de cada peça: secções, instruções, artigos do CCP, condições por procedimento e tipo de contrato |
| `data/` | Documentos de origem (não versionados) |
| `index/` | Índice gerado (não versionado) |

## Confidencialidade

- Os embeddings e o índice são sempre locais.
- O LLM corre num servidor interno (Ollama/vLLM). Em alternativa, pode usar-se Azure OpenAI numa região
  UE com retenção de dados desativada, decisão que cabe à organização e ao seu encarregado de proteção
  de dados (EPD/DPO).
- **Não usar o Streamlit Community Cloud** (alojamento gratuito da Streamlit): os documentos ficariam em
  servidores externos. A aplicação deve ser instalada num servidor da organização (ver Docker abaixo).
- Definir `APP_PASSWORD` e, de preferência, disponibilizar a aplicação apenas na rede interna ou por VPN.

## Instalação no servidor (Docker)

```bash
cp .env.example .env               # ajustar LLM_MODEL e APP_PASSWORD
docker compose up -d
docker compose exec ollama ollama pull bge-m3
docker compose exec ollama ollama pull qwen2.5:32b   # ou o modelo definido em LLM_MODEL
```

A aplicação fica disponível em `http://<servidor>:8501`.

**Requisitos orientativos para o LLM:** modelos de 7–8B parâmetros funcionam para testes mas têm qualidade
jurídica limitada. Para produção recomenda-se 24–32B (≈ 24 GB de VRAM) ou 70B (≈ 48 GB de VRAM).

## Desenvolvimento local

```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt pytest
cp .env.example .env
# Ollama instalado localmente: ollama pull bge-m3 && ollama pull qwen2.5:7b
streamlit run app/streamlit_app.py
pytest
```

## Carregar documentos

Pela página **Base documental**, ou pela linha de comandos:

```bash
# CCP: usar exatamente --diploma CCP (os templates referem artigos deste diploma)
python -m rag.ingest data/legislacao/CCP_consolidado.pdf --fonte legislacao --diploma CCP

# Peças anteriores, organizadas por tipo de peça
python -m rag.ingest data/pecas/cadernos_encargos/ --fonte peca --tipo-peca caderno_encargos \
    --tipo-procedimento concurso_publico --tipo-contrato aquisicao_servicos --ano 2025
```

Tipos de peça válidos: `decisao_contratar`, `programa_procedimento`, `convite`, `caderno_encargos`,
`relatorio_preliminar`, `relatorio_final`, `minuta_contrato`.

**Fontes recomendadas:** CCP consolidado (Diário da República), Portaria das plataformas eletrónicas,
Diretivas 2014/24/UE e 2014/25/UE, orientações do IMPIC, jurisprudência e recomendações do Tribunal de
Contas, e peças anteriores aprovadas pela organização (quanto mais e melhores, melhor o resultado).

## Personalizar templates

Cada ficheiro em `templates/` define uma peça:

```yaml
- id: penalidades
  titulo: Penalidades contratuais
  instrucoes: Fixa as penalidades contratuais por incumprimento, respeitando os limites legais.
  pesquisa: sanções contratuais penalidades limite      # termos extra para a pesquisa
  base_legal: [329]                                      # artigos do CCP enviados sempre como contexto
  condicao: {tipo_contrato: [aquisicao_servicos]}        # opcional
  opcional: true                                         # não selecionada por omissão
```

As referências em `base_legal` são um ponto de partida e **devem ser validadas por um jurista**, sobretudo
depois de alterações ao CCP.

## Próximos passos

- [ ] Validação jurídica dos templates e das referências `base_legal`
- [ ] Carregar o CCP e as peças da organização e avaliar a qualidade com casos reais
- [ ] Anonimização opcional de peças antigas antes da indexação
- [ ] Autenticação integrada (SSO/LDAP) e registo de utilização
- [ ] Verificação automática de que os artigos citados no texto gerado existem no índice
