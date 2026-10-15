# Audio-PDF: Requisitos e Documentação (15/out/2026)

## 1. Visão geral
Aplicação web que recebe o PDF de um livro e devolve um audiobook narrado no idioma escolhido,
traduzindo quando o idioma de saída difere do original. Fluxo: upload → extração/limpeza (OCR se
escaneado) → tradução opcional → TTS por capítulo → MP3/M4B.

**Público:** leitores que preferem ouvir; pessoas com deficiência visual/dislexia; estudantes de
idiomas; autores independentes.

| Dentro do MVP | Fora (por enquanto) |
|---|---|
| PDF com texto e escaneado (OCR) | EPUB, DOCX, MOBI |
| Detecção automática de idioma | Tradução revisada por humanos |
| Tradução para idiomas do provedor | Clonagem de voz do usuário |
| Escolha de voz e velocidade | Várias vozes por personagem |
| MP3 por capítulo e M4B com capítulos | App móvel nativo |
| Player web e download | Distribuição em lojas |

**Premissas:** processamento assíncrono; tradução e TTS em nuvem ou local atrás de interface comum.

## 2. Requisitos funcionais (Must / Should / Could)
| ID | Requisito | Prio |
|---|---|---|
| **Conta** | | |
| RF-01 | Cadastro e login por e-mail e senha | Must |
| RF-02 | Login social (Google) | Should |
| RF-03 | Recuperação de senha por e-mail | Must |
| RF-04 | Biblioteca pessoal | Must |
| **Upload e análise** | | |
| RF-05 | Upload por arrastar/soltar, com barra de progresso | Must |
| RF-06 | Validar tipo, tamanho, proteção por senha, com erro claro | Must |
| RF-07 | Detectar texto selecionável vs escaneado; OCR quando necessário | Must |
| RF-08 | Detectar idioma de origem, com correção manual | Must |
| RF-09 | Estimativa de duração, caracteres e custo/créditos | Should |
| **Extração e limpeza** | | |
| RF-10 | Remover cabeçalhos, rodapés, nº de página, marcas d'água | Must |
| RF-11 | Juntar hifenização e reconstruir parágrafos | Must |
| RF-12 | Capítulos por sumário (bookmarks) ou heurística | Must |
| RF-13 | Notas de rodapé, tabelas, legendas: ler, pular ou ler no fim do capítulo | Should |
| RF-14 | Tela de revisão de texto e divisão de capítulos | Should |
| RF-15 | Selecionar intervalo de páginas/capítulos | Should |
| **Idioma e tradução** | | |
| RF-16 | Escolher idioma de saída | Must |
| RF-17 | Traduzir preservando a estrutura de capítulos | Must |
| RF-18 | Glossário por livro | Could |
| RF-19 | Baixar texto traduzido (TXT/EPUB) | Could |
| **Voz e narração** | | |
| RF-20 | Escolher voz (gênero, sotaque), com amostra de 10 s | Must |
| RF-21 | Velocidade 0,75x–1,5x | Should |
| RF-22 | Pausas entre parágrafos/capítulos e anunciar título | Must |
| RF-23 | Pronúncia personalizada (SSML) | Could |
| **Processamento** | | |
| RF-24 | Conversão em segundo plano, progresso por etapa e capítulo | Must |
| RF-25 | Notificar por e-mail/app ao concluir ou falhar | Should |
| RF-26 | Cancelar e reprocessar conversão ou só um capítulo | Must |
| **Saída e reprodução** | | |
| RF-27 | MP3 por capítulo e M4B único com capítulos e capa | Must |
| RF-28 | Player: capítulos, velocidade, ±30 s, retomada | Must |
| RF-29 | Download individual ou ZIP | Must |
| RF-30 | Excluir livro e todos os arquivos | Must |

## 3. Requisitos não funcionais (metas a confirmar)
| ID | Categoria | Requisito |
|---|---|---|
| RNF-01 | Desempenho | Upload até 200 MB e 1.000 páginas |
| RNF-02 | Desempenho | 300 páginas com texto em até 30 min (sem fila) |
| RNF-03 | Desempenho | Primeiro capítulo audível antes do fim do livro |
| RNF-04 | Escalabilidade | Workers horizontais sem mudar código |
| RNF-05 | Confiabilidade | Idempotente, retomado por capítulo |
| RNF-06 | Confiabilidade | Retentativas com backoff exponencial (máx. 5) |
| RNF-07 | Disponibilidade | 99,5% mensal |
| RNF-08 | Áudio | MP3 44,1 kHz, 128 kbps mono, -16 LUFS |
| RNF-09 | Texto | Erro de OCR < 3% (300 dpi) |
| RNF-10 | Segurança | HTTPS; criptografia em repouso; URLs assinadas com expiração |
| RNF-11 | Segurança | Argon2/bcrypt; proteção contra força bruta e rate limit |
| RNF-12 | Privacidade | LGPD/GDPR; PDFs originais apagados após 30 dias |
| RNF-13 | Isolamento | Verificação de dono em toda rota |
| RNF-14 | Usabilidade | Responsivo; PT e EN |
| RNF-15 | Acessibilidade | WCAG 2.1 AA |
| RNF-16 | Manutenibilidade | Provedores OCR/tradução/TTS em adapters |
| RNF-17 | Manutenibilidade | Cobertura ≥ 70% no backend |
| RNF-18 | Observabilidade | Logs estruturados, métricas por etapa, erros |
| RNF-19 | Custo | Custo por conversão; cache de tradução e TTS |
| RNF-20 | Legal | Termos de uso; uso pessoal apenas |

## 4. Arquitetura
API só registra jobs; workers assíncronos processam um capítulo por vez. PDF sobe direto ao S3 por
URL assinada; workers gravam progresso no PostgreSQL; frontend acompanha por SSE.

Pipeline (cada etapa grava resultado no S3; falha retoma da última concluída):
1. **Extrair** — PyMuPDF: texto, sumário, posição; páginas sem texto marcadas para OCR
2. **OCR** — OCRmyPDF/Tesseract
3. **Limpar e dividir** — cabeçalhos, hifenização, idioma de origem, capítulos
4. **Traduzir** — se necessário; blocos com contexto anterior e glossário; cache por hash
5. **Narrar** — trechos por frase, SSML com pausas, TTS em paralelo
6. **Empacotar** — FFmpeg: concat, normalização, MP3 por capítulo e M4B

## 5. Stack
| Camada | Recomendada | Alternativas |
|---|---|---|
| Frontend | Next.js + TS + Tailwind | Nuxt, SvelteKit |
| API | FastAPI (Python 3.12) | Django REST, NestJS |
| Fila | Celery + Redis | RQ, Dramatiq, SQS |
| Banco | PostgreSQL | MySQL |
| Storage | S3 (MinIO em dev) | GCS, R2 |
| Extração | PyMuPDF | pdfplumber, pdfminer.six |
| OCR | Tesseract/OCRmyPDF | Document AI, Textract, Azure DI |
| Idioma | lingua-py | fastText, langdetect |
| Tradução | DeepL API | Google Translate, Claude, NLLB/MarianMT |
| TTS | Azure AI Speech | Google, Polly, ElevenLabs, OpenAI, Piper/XTTS |
| Áudio | FFmpeg + mutagen | pydub |
| Auth | JWT + refresh; OAuth Google | Auth.js, Keycloak, Clerk |
| Infra | Docker Compose; K8s/containers gerenciados | Render, Fly.io, Railway |
| Observabilidade | OpenTelemetry, Prometheus/Grafana, Sentry | Datadog |

## 6. Modelo de dados
`User`, `Book`, `Chapter`, `ConversionJob`, `ChapterTask`, `AudioOutput`, `PlaybackProgress`,
`GlossaryEntry`, `TranslationCache` (campos no documento original).

Status do job: `queued → extracting → ocr → awaiting_review (opcional) → translating →
synthesizing → packaging → done`, ou `failed` / `canceled`.

### API REST (`/api/v1`)
| Método | Rota | Função |
|---|---|---|
| POST | /auth/register, /auth/login, /auth/refresh | Conta e sessão |
| POST | /books/upload-url | URL pré-assinada |
| POST | /books | Registra livro e dispara análise |
| GET | /books, /books/{id} | Biblioteca e detalhes |
| GET/PATCH | /books/{id}/chapters | Ler/editar capítulos |
| DELETE | /books/{id} | Exclui livro e arquivos |
| GET | /languages | Idiomas de saída |
| GET | /voices?language= | Vozes com amostra |
| POST | /books/{id}/jobs | Inicia conversão |
| GET | /jobs/{id} | Status e progresso |
| GET | /jobs/{id}/events | SSE |
| POST | /jobs/{id}/cancel, /jobs/{id}/chapters/{n}/retry | Cancelar/reprocessar |
| GET | /jobs/{id}/outputs | Links assinados |
| PUT | /jobs/{id}/progress | Posição do player |

## 7. Fluxo principal
Novo audiobook → upload → análise (título, páginas, escaneado, idioma, capítulos) → idioma, voz,
velocidade → estimativa e confirmação → (revisão) → conversão em segundo plano → notificação,
player ou download.

Exceções: PDF com senha; OCR de baixa confiança; idioma sem voz; falha em capítulo (parcial +
reprocessar).

Telas: Login/cadastro · Biblioteca · Novo audiobook · Revisão de texto · Progresso · Player · Conta.

## 8. Segurança, direitos autorais, custos, testes, deploy
- **Segurança:** upload por URL assinada com revalidação (%PDF); PDFs só em workers isolados
  (sem rede interna, limite de memória/tempo); segredos em cofre; verificação de dono; UUIDs; rate limits.
- **Direitos autorais:** exigir confirmação de direito sobre o conteúdo; uso pessoal; sem link
  público; canal de denúncia; consulta jurídica antes de lançar.
- **Custos (aprox., confirmar):** 600 mil caracteres/livro → TTS ~US$ 10; tradução ~US$ 12–15;
  OCR em nuvem < US$ 1.
- **Testes:** unitário, integração (mocks + 10–20 PDFs), contrato, E2E (Playwright), qualidade
  (amostragem), carga (50 livros).
- **Deploy:** dev em Docker Compose (frontend, API, worker, PostgreSQL, Redis, MinIO); prod em
  containers/K8s com autoescala; CI/CD GitHub Actions.

## 9. Roadmap
0. PoC: CLI PDF com texto → MP3 por capítulo · 1. MVP web (Must) · 2. Refinamento (Should) ·
3. Expansão (Could, EPUB/DOCX, planos, app).

## Questões em aberto
Modelo de preço · idiomas prioritários no lançamento · nuvem vs modelos locais no MVP.
