# การเชื่อมต่อโมเดล

## Gateway และ API key

ตั้งค่าได้ใน Super Admin → โมเดลและบริการ AI URL ต้องเป็น API base ที่ API/worker เข้าถึงได้ (รวม `/v1` ตาม Gateway) API key ถูกเข้ารหัสในฐานข้อมูลด้วย `SECRETS_KEY` และไม่ส่งกลับเบราว์เซอร์ คีย์เข้ารหัสอยู่ใน `.env` ที่ถูกละเว้นจาก Git ต้องเก็บและสำรองอย่างปลอดภัย หากเปลี่ยนโดยไม่ย้ายข้อมูล key เก่าจะถอดรหัสไม่ได้

ใช้ปุ่มทดสอบการเชื่อมต่อเพื่อเรียก `/models` แล้วเพิ่ม alias ที่มีจริงในหมวด LLM/Image/Video/STT/TTS/Embedding/Reranker ก่อนเปิดใช้งาน ไม่ seed ชื่อโมเดลสมมติ ราคา input/output เป็น USD ต่อ 1M tokens ที่ผู้ดูแลกำหนด

การสร้าง Site ครั้งนี้ไม่ได้ตั้งค่า Gateway ภายนอกหรือเรียก paid APIs ผู้ใช้ต้องระบุ key และเลือกโมเดลจริงก่อนใช้งาน

## LLM

เรียก `/chat/completions` แบบ `stream: true` อ่าน SSE แบบ incremental และบันทึก usage ที่ upstream รายงาน โมเดลต้องได้รับอนุญาตตาม tenant policy หากไม่กำหนดจะใช้โมเดลที่เปิดใช้งาน โมเดลสำรองลองได้หนึ่งโมเดล LLM ที่องค์กรอนุญาตเมื่อ primary ล้มเหลวก่อนส่งข้อความ ไม่สลับหลังเริ่มตอบ

แชทใช้ข้อความล่าสุดไม่เกิน 8 ข้อความ และ context ที่ค้นได้ในคลังที่ผู้ใช้มีสิทธิ์ ไม่มีหลักฐานจะไม่เรียกโมเดลและไม่สร้างแหล่งอ้างอิงสมมติ `extractive-demo` คือข้อความจากเอกสารที่มีป้ายกำกับ ไม่ใช่คำตอบ paid LLM

## Media

- Image: `POST /images/generations` รองรับ `b64_json` หรือ HTTPS URL จาก host ที่อนุญาตใน `MEDIA_DOWNLOAD_HOSTS` ไม่มีการตาม redirect และไม่ส่ง Gateway key ไป host รูปภาพ
- STT: `POST /audio/transcriptions` ส่ง multipart file สูงสุด 20 MB
- TTS: `POST /audio/speech` ใช้ voice ID ที่โมเดลรองรับ ผลลัพธ์ MP3
- Video: `POST /videos` → `GET /videos/{id}` → `GET /videos/{id}/content` ความยาว/ขนาดต้องรองรับตาม provider

งานบันทึกใน PostgreSQL ประมวลผลด้วย Celery และเก็บผลใน SeaweedFS Preview/download ตรวจทั้ง tenant และเจ้าของงาน ค่าใช้จ่ายใช้ `x-litellm-response-cost` ถ้ามี มิฉะนั้นแสดงว่ายังไม่ทราบราคา ไม่สร้างผลลัพธ์จำลองแทนผู้ให้บริการ

## หลายผู้ให้บริการ (Google AI, OpenRouter)

หน้า "โมเดลและบริการ AI" มีส่วน "ผู้ให้บริการโมเดล" ให้ใส่ API key แยกรายผู้ให้บริการ (เข้ารหัสด้วย `SECRETS_KEY`, ไม่ส่งกลับ) `Google AI` ใช้ endpoint OpenAI-compatible `https://generativelanguage.googleapis.com/v1beta/openai` และ `OpenRouter` ใช้ `https://openrouter.ai/api/v1` โมเดลจะเรียกผ่านผู้ให้บริการที่ตรงกับช่อง "ผู้ให้บริการ" ของโมเดล หากไม่มี key ของรายนั้นจะใช้ Gateway หลัก

โมเดลสำรองจะเลือกโมเดลชื่อเดียวกันจากผู้ให้บริการอื่นก่อน แล้วจึงเลือกตัวที่ราคาถูกที่สุด เช่น Gemini 3.5 Flash Lite บน Google AI (`gemini-3.5-flash-lite`) สำรองด้วยตัวเดียวกันบน OpenRouter ใช้ปุ่ม "ทดสอบ" เพื่อดูรหัสโมเดลที่ผู้ให้บริการมีจริงก่อนเปิดใช้ รหัส `gemini-3.1-flash-lite` และรหัสบน OpenRouter (`google/...`) ยังไม่ได้ยืนยันกับผู้ให้บริการ ระบบไม่จำกัด RPM/RPD ฝั่งเรา โควตาฟรีของ Google (เช่น 15 RPM / 500 RPD) จึงอาศัยโมเดลสำรองเมื่อได้ 429

## LLM ในเครื่อง (Qwen 3.5 2B)

บริการ `llm-local` (llama.cpp, CPU, profile `llm-local` — ตั้ง `COMPOSE_PROFILES=llm-local` ใน `.env`) โหลด `Qwen3.5-2B-Q4_K_M.gguf` จาก `unsloth/Qwen3.5-2B-GGUF` (~1.3 GB) ครั้งแรกลง volume `gguf` เปิดโหมดไม่คิดยาว (`--reasoning-budget 0`) ปรับด้วย `LLM_LOCAL_THREADS` / `LLM_LOCAL_CONTEXT` (ค่าปริยาย 4 / 8192) ผู้ให้บริการ `Local LLM` ไม่ต้องใช้ API key (URL จาก `LOCAL_LLM_URL`) เพิ่มโมเดลด้วย model ID `qwen3.5-2b` แล้วอนุญาตในนโยบายโมเดลขององค์กร

## Learned embeddings / reranking

ค่าปริยายใช้ hash embedding CPU 256 dimensions ใน `hub_hash_ngram_v1_256` หากต้องการ learned model ให้ตั้ง `EMBEDDING_MODEL`, `EMBEDDING_DIMENSIONS`, `EMBEDDING_VERSION` และตั้ง Gateway ก่อน recreate API/worker แล้ว reindex เอกสาร ระบบใช้ `/embeddings` ครั้งละสูงสุด 32 ข้อความและตรวจ dimensions/finite values สร้างชื่อ collection จาก fingerprint ของ model/dimensions/version ไม่ผสม embedding spaces

### โมเดลในเครื่อง (ONNX, CPU)

- `EMBEDDING_MODEL=local:multilingual-e5-small` — 384 มิติ ใช้คำนำหน้า `query: `/`passage: ` เกณฑ์ cosine ขั้นต่ำ `EMBEDDING_MIN_SCORE` (0.80) เปลี่ยนโมเดลแล้วต้อง reindex
- `RERANK_MODEL=local:bge-reranker-v2-m3` — ONNX INT8 571 MB ตัดผลที่คะแนนต่ำกว่า `RERANK_MIN_SCORE` (0..1, 0 = ไม่ตัด)
- โมเดลดาวน์โหลดจาก HuggingFace ครั้งแรกลง `DATA_DIR/models` (volume `api-data`) ปรับเธรดด้วย `ONNX_THREADS`, ขนาดแบตช์ด้วย `ONNX_BATCH_SIZE` / `ONNX_RERANK_BATCH_SIZE`
- OCR ใช้ PaddleOCR PP-OCRv5 ภาษาไทย (`OCR_LANGUAGES`)

ตั้ง `RERANK_MODEL` เพื่อเรียก `/rerank` หลังรวม BM25 และ dense rankings ตรวจ index ของผลลัพธ์ก่อนนำมาใช้งาน ไม่มีการให้ reranker ขยายสิทธิ์เข้าถึงเอกสาร

## การยืนยันผล

Adapters ของ LLM/media/embedding/reranker ผ่าน automated mocked-provider tests การยืนยันกับโมเดลจริงและคุณภาพภาษาไทยต้องทำหลังมี credentials ดู verification.md และ feature-status.md
