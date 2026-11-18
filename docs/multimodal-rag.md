# Multimodal RAG

Pictures in your documents (charts, diagrams, scanned pages, photos) become searchable, and a vision-capable model can look at them when it answers. It is **off by default** because pictures and the text of questions are sent to Google AI.

## How it works

| Level | What happens | Where |
| --- | --- | --- |
| 1. Describe | Each picture (an uploaded image, or a PDF page that contains a figure) is described in Thai by a vision model. The description is stored as a normal chunk (`kind = image`), so BM25, the text embedding and the reranker find it like any text. | `multimodal.index_pictures`, `retrieval.ingest` |
| 2. Embed | The picture itself is embedded with a multimodal embedding model (`gemini-embedding-2`, 768 dimensions) that shares one vector space with text. Search adds "question text vs picture vectors" as a third ranking before RRF fusion. Vectors are stored in their own Qdrant collection and in PostgreSQL (so search also works without Qdrant). | `retrieval.picture_hits` |
| 3. Show | If the answering model can see images (Gemini on Google AI, or an OpenRouter model that lists `image` as an input), the best picture chunks are sent to it with the evidence. Other models get the description only. | `chat_service`, `multimodal.with_images` |

Citations of a picture carry `kind: "image"`; the web UI marks them with a picture icon. Storage keys never reach the browser.

## Turn it on

Two switches: `MULTIMODAL_RAG=true` makes the feature available (and needs a Google AI key), and each **knowledge base** opts in on its own (Knowledge bases, edit, Multimodal). Only opted-in libraries are sent to Google, so a library without charts or diagrams costs nothing. After changing a library's switch, press **Update documents** (or `POST /api/knowledge-bases/{id}/multimodal/apply`): only the documents whose pictures must change are re-indexed (switch on: files that contain pictures and have none indexed yet; switch off: files that still hold picture chunks).

```bash
# .env  (needs GOOGLE_AI_API_KEY, or a key saved for the Google AI provider)
MULTIMODAL_RAG=true
docker compose up -d api worker
```

Existing documents are not touched until you apply the switch to the library.

| Variable | Default | Meaning |
| --- | --- | --- |
| `MULTIMODAL_RAG` | `false` | master switch |
| `MM_CAPTION_MODEL` | `gemini-3.5-flash-lite` | vision model that writes the descriptions |
| `MM_EMBED_MODEL` / `MM_EMBED_DIMS` | `gemini-embedding-2` / `768` | picture and query embedding (own Qdrant collection per model and size) |
| `MM_MAX_IMAGES` | `12` | pictures indexed per document (first pages with a figure) |
| `MM_MIN_SCORE` | `0.38` | minimum similarity for a picture to be a candidate |
| `MM_ANSWER_IMAGES` | `2` | pictures sent to the answering model |

## Limits and privacy

- Pictures, their descriptions and question text leave the machine (Google AI). Keep it off for confidential material, or use text-only models and `MULTIMODAL_RAG=false`.
- A PDF page that contains a figure is indexed as a whole page image (figures smaller than 150 x 150 px, such as logos, are ignored). Pictures inside DOCX, PPTX and spreadsheets are not extracted yet.
- If the vision service fails or a quota is hit, the document is still indexed as text; the picture is skipped and a warning is logged.
- `MM_MIN_SCORE` was set from a small sample (about 0.47 for a matching question against a figure, 0.28 to 0.32 for unrelated ones). Re-measure it on your own documents.
- An image file with no readable text becomes unindexable when its library's switch is turned off (it has nothing but its description), so that document shows as failed until it is deleted or the switch is turned back on.
- Reasoning models (for example the Muse, Hy4 and Kimi families) can use the whole output budget on hidden reasoning and return no answer. Set the model's reasoning effort to `low` in Super Admin, Models.

## Search page

Picture chunks are listed with their real figure as the thumbnail (`GET /api/chunks/{id}/image`, same access rule as the document). The page asks for `limit` candidates (default `SEARCH_CANDIDATES=20`) and at most `SEARCH_PER_DOC=3` passages per document, because the reranker is a CPU model: 50 candidates took about 12 s, 20 take about 5 s and keep every document of the 50-passage list. Passages the reranker finds barely related (below `SEARCH_MIN_SCORE=0.03`) are hidden.
