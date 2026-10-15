# Análise da documentação — pontos a resolver antes do MVP web

## Inconsistências
1. **OCR × idioma:** OCR usa o idioma detectado como dica, mas a detecção vem depois do OCR.
   Proposta: OCR de 2–3 páginas de amostra multi-idioma → detectar → OCR completo.
2. **Status do job:** falta `partial` (falha em capítulo); `awaiting_review` precede `translating`,
   não cobre revisão da tradução.
3. **Retenção × reprocessamento:** RNF-12 apaga o PDF em 30 dias; RF-26 permite reprocessar.
   Definir se `source_text_key` vira a fonte após 30 dias.
4. **ChapterTask:** mistura etapas de livro (extrair, OCR) e de capítulo. Separar `BookTask`.
5. **Cache × privacidade:** `TranslationCache` global vaza conteúdo entre usuários (RNF-12/13/RF-30).
   Falta cache de TTS (RNF-19).
6. **Armazenamento:** ~11 h por livro ≈ 630 MB de MP3; com ZIP + M4B ≈ 1,3 GB + egress. Não é "centavos".

## Lacunas
- Entidades: créditos/plano/transações, consentimento LGPD, Notification, reset de senha, refresh token, denúncias.
- Endpoints: aprovar revisão (`POST /jobs/{id}/approve`), recuperação de senha.
- SSE com JWT: `EventSource` não envia `Authorization` → cookie httpOnly ou token curto.
- PDF com senha: senha só em memória, nunca em log.
- Limite de TTS por requisição definido no adapter.
- Loudness: por capítulo ou por livro (consistência no M4B)?

## Questões de negócio em aberto
Modelo de preço · idiomas prioritários · nuvem × local no MVP.
