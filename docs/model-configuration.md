# Model connections

## Gateway and API keys

Configure them in Super Admin → AI models and services. The URL must be an API base reachable from the API and the worker (including `/v1` for a gateway). API keys are encrypted in the database with `SECRETS_KEY` and never sent back to the browser. The encryption key lives in `.env`, which Git ignores; store and back it up safely. If it changes without migrating the data, the old keys cannot be decrypted.

Use the connection test button to call `/models`, then add the aliases that really exist under LLM / Image / Video / STT / TTS / Embedding / Reranker before enabling them. No imaginary model names are seeded. Input and output prices are USD per 1M tokens, set by the administrator.

This site was created without an external gateway and without calling any paid API. You must supply a key and choose real models before use.

## LLM

The system calls `/chat/completions` with `stream: true`, reads SSE incrementally and records the usage the upstream reports. A model must be allowed by the organisation's model policy; if none is set, the enabled models are used. A fallback model may try one permitted LLM when the primary fails before any text is sent; it never switches after the answer has started.

Chat uses at most the latest 8 messages plus the context retrieved from knowledge bases the user may read. With no evidence the model is not called and no sources are invented. `extractive-demo` returns labelled text from the documents; it is not a paid LLM answer.

## Media

- Image: `POST /images/generations`, supporting `b64_json` or an HTTPS URL from a host allowed in `MEDIA_DOWNLOAD_HOSTS`. Redirects are not followed and the gateway key is never sent to the image host.
- STT: `POST /audio/transcriptions`, sending a multipart file up to 20 MB.
- TTS: `POST /audio/speech`, using a voice ID the model supports; the result is MP3.
- Video: `POST /videos` → `GET /videos/{id}` → `GET /videos/{id}/content`; length and size must be supported by the provider.

Jobs are stored in PostgreSQL, processed by Celery and their results kept in SeaweedFS. Preview and download check both the organisation and the job owner. Cost uses `x-litellm-response-cost` when present; otherwise the price is shown as unknown. No simulated result replaces the provider.

## Several providers (Google AI, OpenRouter)

The "AI models and services" page has a "Model providers" section for one API key per provider (encrypted with `SECRETS_KEY`, never returned). `Google AI` uses the OpenAI-compatible endpoint `https://generativelanguage.googleapis.com/v1beta/openai` and `OpenRouter` uses `https://openrouter.ai/api/v1`. A model is called through the provider named in its "Provider" field; if that provider has no key, the main gateway is used.

A fallback prefers the model with the same name at another provider, then the cheapest one. For example, Gemini 3.5 Flash Lite on Google AI (`gemini-3.5-flash-lite`) falls back to the same model on OpenRouter. Use the "Test" button to see the model IDs the provider really offers before enabling them. The ID `gemini-3.1-flash-lite` and the OpenRouter IDs (`google/...`) have not been confirmed with the providers. There is no RPM/RPD limit on our side, so Google's free quota (for example 15 RPM / 500 RPD) relies on the fallback model after an HTTP 429.

## Local LLM (Qwen 3.5 2B)

The `llm-local` service (llama.cpp, CPU, profile `llm-local` — set `COMPOSE_PROFILES=llm-local` in `.env`) downloads `Qwen3.5-2B-Q4_K_M.gguf` from `unsloth/Qwen3.5-2B-GGUF` (about 1.3 GB) into the `gguf` volume on first start. Long thinking is off (`--reasoning-budget 0`). Tune it with `LLM_LOCAL_THREADS` / `LLM_LOCAL_CONTEXT` (defaults 4 / 8192). The `Local LLM` provider needs no API key (URL from `LOCAL_LLM_URL`). Add a model with model ID `qwen3.5-2b` and allow it in the organisation's model policy. Local models cannot be used in Agent mode, which requires tool calling.

## Gemini Decision 1 (optional)

`gemini-decision-1` is not a chat model: it answers typed yes/no, choice and score questions with calibrated probabilities through the Decisions API (`POST /v1beta/decisions`), so it is not added in the model list. Set `DECISIONS_ENABLED=true` with a Google AI key (`GOOGLE_AI_API_KEY`) and it is used in three places:

1. **Relevance gate**: before answering, it judges whether the retrieved passages answer the question; below `DECISIONS_RELEVANCE_MIN` (0.25) the chat replies "no evidence found" instead of letting a small model summarise unrelated text.
2. **Citation check**: one batched call tells which passage supports each cited statement; otherwise the local n-gram check is used.
3. **Library suggestion**: `GET /api/documents/{id}/suggest-library` returns the best knowledge base the user may write to (no screen uses it yet).

Choose the model with `DECISIONS_MODEL`: `gemini-decision-1` (Google AI key) or, through OpenRouter's alpha Decisions API (`OPENROUTER_API_KEY`), `typesafe/jev-1.14`, `typesafe/jev-1.13` or `perplexity/pplx-decider-v1.2`. An id with a `/` goes to OpenRouter. The OpenRouter dialect was written from its documentation and has not been tried against the live service. Calibration differs between models, so check `DECISIONS_RELEVANCE_MIN` with real questions after switching.

If the service is off, slow (`DECISIONS_TIMEOUT`, 12 s) or fails, the local method is used and Decision 1 is skipped for two minutes. Questions and passages are sent to Google AI while it is on.

## Learned embeddings and reranking

The default is a 256-dimension CPU hash embedding in `hub_hash_ngram_v1_256`. For a learned model, set `EMBEDDING_MODEL`, `EMBEDDING_DIMENSIONS` and `EMBEDDING_VERSION` and configure the gateway, then recreate the API and worker and reindex the documents. The system calls `/embeddings` with at most 32 texts at a time, validates dimensions and finite values, and derives the collection name from a fingerprint of model, dimensions and version so embedding spaces are never mixed.

### Local models (ONNX, CPU)

- `EMBEDDING_MODEL=local:multilingual-e5-small` — 384 dimensions, uses the `query: ` / `passage: ` prefixes, with a minimum cosine threshold `EMBEDDING_MIN_SCORE` (0.80). Reindex after changing the model.
- `RERANK_MODEL=local:bge-reranker-v2-m3` — ONNX INT8, 571 MB. Results scoring below `RERANK_MIN_SCORE` (0..1, 0 = keep all) are dropped. A value of `0.01` is recommended from `make eval` measurements (out-of-scope questions score at most 0.003, while 0.1 would discard about 9% of correct answers).
- Models download from HuggingFace on first use into `DATA_DIR/models` (the `api-data` volume). Tune threads with `ONNX_THREADS` and batch sizes with `ONNX_BATCH_SIZE` / `ONNX_RERANK_BATCH_SIZE`.
- OCR uses PaddleOCR PP-OCRv5 for Thai (`OCR_LANGUAGES`).

Set `RERANK_MODEL` to call `/rerank` after merging the BM25 and dense rankings. The result indexes are validated before use, and the reranker never widens document access.

## Verification

The LLM, media, embedding and reranker adapters pass automated mocked-provider tests. Verification with real models and the quality of Thai answers must be done once credentials exist. See verification.md and feature-status.md.
