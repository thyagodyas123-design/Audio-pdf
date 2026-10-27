# Proposta: vídeo e conteúdo de estudo (próximos passos da branch)

Base já pronta nesta branch: **linha do tempo** (cada trecho narrado ↔ parágrafo ↔ região do PDF) e **imagem de cada página**.

## 1. Vídeo "leitura acompanhada" (local, sem IA generativa) — IMPLEMENTADO
Também implementado: *vídeo resumo* extrativo (`summarize.py`): escolhe ~20% dos parágrafos mais representativos e os narra; não reescreve.
Para cada capítulo: quadros = página do PDF com o parágrafo em destaque, duração = a do trecho narrado; trilha = o MP3 do capítulo.
`ffmpeg` (concat demuxer) monta o MP4. Entrada: `NN.timeline.json` + `pages/` + `align.json`. Estimativa: poucos minutos por capítulo.
Limite: mostra o PDF, não "explica" o conteúdo (não cria diagramas nem exemplos novos).

## 2. Vídeo explicativo (exige LLM) — IMPLEMENTADO como "vídeo-aula"
Roteiro por LLM em blocos de ~5,5 mil caracteres (até 14 cenas) + introdução, resumo e 3 perguntas; JSON validado, uma nova tentativa se inválido.
O LLM só vê o texto do capítulo e devolve a referência dos parágrafos que sustentam cada cena (usados para destacar o PDF).
Pendente: validar a qualidade com um LLM real (a conta usada nos testes estava sem créditos).
Roteiro por capítulo (resumo em blocos), slides gerados (HTML → imagens) e narração do roteiro, não do texto integral.
Depende de um modelo de linguagem: Claude via API (`ANTHROPIC_API_KEY`) ou modelo local. Sem chave, não dá para validar a qualidade.

## 3. Conteúdo de estudo (exige LLM)
Por capítulo: resumo, pontos-chave, glossário, flashcards e perguntas com gabarito, sempre citando o parágrafo/página de origem
(o alinhamento permite "ver no PDF"). Armazenar em `NN.study.json`; tela "Estudar" com flashcards e quiz; revisão espaçada simples (localStorage).
Mesmo adapter de tradução/LLM; testes com cliente falso, como nos tradutores.

## Decisões em aberto
- Qual LLM usar (Claude por API ou local) e orçamento por livro.
- Vídeo: apenas leitura acompanhada, ou também explicativo?
