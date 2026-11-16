# AI Knowledge Hub

เว็บไซต์ภาษาไทยสำหรับจัดการความรู้และถามคำถามจากเอกสาร ออกแบบตามภาพใน `../user ui` และ `../admin ui` พร้อม User Portal และ Super Admin Console

เวอร์ชันนี้เป็น **ระบบที่รันได้สำหรับพัฒนาและเชื่อมต่อบริการ AI จริง** มีฐานข้อมูล API และการประมวลผลไฟล์จริง ยังไม่ครบทุกความสามารถใน Master Build Prompt และยังไม่ใช่ระบบพร้อมใช้งาน Production ดู [รายการข้อจำกัด](docs/limitations.md)

## เปิดใช้งาน

เว็บ: **http://localhost:3009** หรือ http://127.0.0.1:3009

OpenAPI / Swagger: **http://localhost:8100/docs**

ฟีเจอร์ล่าสุด: แชทเลือกได้ว่าจะตอบจากเอกสารหรือคุยกับ AI ทั่วไป, แนบไฟล์กับคำถาม (PDF, Word, Excel, PowerPoint, TXT, ภาพ), แสดงคำตอบเป็น Markdown/สูตร LaTeX, หลาย provider (Google AI, OpenRouter, Local LLM Qwen 3.5 2B) พร้อมแสดงขีดจำกัดและการใช้งาน, สิทธิ์คลังความรู้รายผู้ใช้, เวอร์ชันเอกสาร, ถังขยะ/กู้คืน, OCR ภาษาไทย/อังกฤษ, Gateway/API key แบบเข้ารหัส, สตรีมคำตอบจากผู้ให้บริการ, โมเดลสำรอง, นโยบายโมเดล/งบประมาณ, งานภาพ/วิดีโอ/STT/TTS, ตั้งค่าบัญชีและจัดการเซสชัน ดู [สถานะฟีเจอร์ล่าสุด](docs/feature-status.md)

กด **เข้าหน้าผู้ใช้งาน** หรือ **เข้า Super Admin** เพื่อทดลองใช้ บัญชีและเอกสารตัวอย่างสร้างเฉพาะเมื่อ `DEMO_MODE=true` ปุ่มทดลองเข้าใช้งานให้สิทธิ์กับข้อมูลสาธิต จึงเปิดบริการพัฒนาไว้เฉพาะ loopback บนเครื่องนี้

### Docker (แนะนำ)

ต้องมี Docker Desktop ที่กำลังทำงาน และ Docker Compose รุ่นที่รองรับ `!override` / `!reset`

```powershell
cd "C:\Users\mongkhonhatit\Downloads\Super AI Enterprise\ai-knowledge-hub"
.\scripts\setup-env.ps1
docker compose config --quiet
docker compose up -d --build
docker compose ps
docker compose logs -f
# หยุดบริการ โดยเก็บฐานข้อมูลและไฟล์ไว้
docker compose down
```

สคริปต์ตั้งค่าสร้างรหัสลับแบบสุ่มใน `.env` และไม่เขียนทับไฟล์ที่มีอยู่ ห้ามเผยแพร่หรือ commit `.env` ไม่ใช้ `docker compose down -v` หากต้องการรักษาข้อมูล

บริการหลัก: Next.js, FastAPI, Celery, PostgreSQL, Redis, Qdrant และ SeaweedFS S3 บริการภายในไม่มี host port ยกเว้นเว็บและ API ที่ผูกกับ `127.0.0.1`

### รันโดยไม่ใช้ Docker

รัน API และเว็บจาก venv แต่ใช้ฐานข้อมูล PostgreSQL ของ Docker (ไม่รองรับ SQLite) เปิดพอร์ตผ่าน `compose.dev.yaml` ที่ผูกกับ `127.0.0.1` เท่านั้น เทสต์และชุดประเมินก็สร้างฐานข้อมูลชั่วคราวบนเซิร์ฟเวอร์เดียวกัน

```powershell
docker compose -f compose.yaml -f compose.dev.yaml up -d postgres
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r apps/api/requirements.txt
cd apps/web
npm.cmd ci
cd ../..
.\scripts\start-local.ps1
```

อย่ารันแบบ local และ Docker พร้อมกันบนพอร์ตเดียวกัน รหัสผ่านบัญชีพัฒนาสุ่มครั้งแรกเก็บใน `apps/api/data/dev-password.txt` สำหรับ local และ `/data/dev-password.txt` ภายใน API container สำหรับ Docker (ไฟล์เหล่านี้ถูกละเว้นจาก Git)

บัญชีพัฒนา: `admin@local.test` (Super Admin), `department@local.test` (ผู้ดูแลแผนก), `member@local.test` (ผู้ใช้) ไม่มีรหัสผ่าน Production ฝังใน source

## งานที่ทดลองได้จริง

1. เข้า Super Admin เพื่อเพิ่มองค์กร กำหนดโควตา และเพิ่มบัญชีผู้ใช้ในองค์กรนั้น
2. เข้าด้วยบัญชีที่สร้างเพื่อใช้พื้นที่องค์กรของตนเอง
3. ผู้ดูแลสร้างคลังความรู้ และสมาชิกอัปโหลด PDF, DOC, DOCX, PPTX, XLS, XLSX, TXT, MD, CSV, HTML, PNG หรือ JPEG (ไม่เกิน 20 MB)
4. รอเอกสารสถานะ “พร้อมใช้งาน” จาก Celery worker ใน Docker
5. ค้นหาแบบ Keyword/BM25, CPU Vector demonstration หรือ Hybrid/RRF
6. สนทนาที่ `/chat` (ดูหัวข้อ “การใช้แชท” ด้านล่าง) เปิดแหล่งอ้างอิงพร้อมเลขหน้า และดาวน์โหลดต้นฉบับ
7. ตรวจประวัติสนทนา รายงานค่าใช้จ่าย Audit log และส่งออก CSV
8. ระงับบัญชีหรือองค์กรได้ โดย API ตรวจสิทธิ์ทุกคำขอ

### การใช้แชท

- **เลือก AI Model ก่อนถาม** ที่มุมขวาของช่องถาม (ไอคอนสมอง) รายการมีเฉพาะโมเดลที่เปิดใช้และมี API key แล้ว ถ้าชื่อซ้ำกันจะต่อท้ายด้วยชื่อ provider เช่น “Gemini 3.5 Flash Lite Google AI” พร้อมแสดง RPM/TPM/RPD และจำนวนที่ใช้ไปแล้ว ถ้าไม่มีโมเดลที่ใช้ได้จะขึ้น “ไม่มี AI Model ที่ใช้งานได้” (ตั้งค่า key ที่ Super Admin → โมเดลและบริการ AI) ระบบจำโมเดลที่เลือกไว้ในเบราว์เซอร์
- **ตอบจากเอกสาร** ค้นเอกสารที่คุณมีสิทธิ์ พร้อมอ้างอิงเลขหน้า ปุ่ม “ทุกคลังความรู้” ใช้จำกัดคลังหรือเลือกเอกสาร
- **คุยทั่วไป** ส่งคำถามให้ LLM ตรง ๆ ไม่ค้นเอกสาร ไม่มีการอ้างอิง (โมเดลสาธิตแบบ extractive ใช้ได้เฉพาะโหมดตอบจากเอกสาร)
- **แนบไฟล์** ปุ่ม “แนบไฟล์” ลากไฟล์มาวาง หรือวางภาพ (Ctrl+V) ได้สูงสุด 5 ไฟล์ ไฟล์ละไม่เกิน 20 MB รองรับ PDF, DOC, DOCX, PPTX, XLS, XLSX, TXT, MD, CSV, HTML, PNG, JPG ระบบแตกข้อความ (ภาพใช้ OCR) เก็บชั่วคราวเฉพาะผู้ใช้นั้น ไม่เข้าดัชนี สแกนไวรัสก่อนใช้ ใช้กับคำถามเดียว และส่งให้โมเดลรวมไม่เกิน `CHAT_ATTACHMENT_CHARS` (ค่าเริ่มต้น 12000) ตัวอักษร ใช้ได้ทั้งสองโหมด
- คำถามและคำตอบแสดง Markdown และสูตร LaTeX (`$…$`, `\(…\)`, `\[…\]`) คำตอบถูกตัดที่ `max_output_tokens` ของหน้า “ประหยัดค่าใช้จ่าย” (ค่าเริ่มต้น 1024)

**โหมดสาธิตไม่ใช้ LLM** คำตอบเป็นการดึงข้อความจากเอกสารที่ค้นพบมาแสดง พร้อมป้ายกำกับชัดเจน ค่าปริยายของ embedding คือ character n-gram hashing สำหรับ CPU ส่วนชุดที่ตั้งไว้ใน `.env` ใช้ `intfloat/multilingual-e5-small` (ONNX) และ reranker `bge-reranker-v2-m3` (ONNX INT8) รันบน CPU ในเครื่อง ไม่ต้องมี GPU ดู [ตั้งค่าโมเดล](docs/model-configuration.md) แยก collection ด้วยชื่อ embedding version

**Gemma 4 (31B / 26B):** ใช้ผ่าน Google AI Studio ด้วย `GOOGLE_AI_API_KEY` เดิม ส่วนที่โมเดลคิด (`<thought>`) จะถูกซ่อนไว้ 31B ช้ากว่า (ค้นเว็บอาจใช้ ~1 นาที)

**ค้นเว็บ (tool calling):** กดปุ่ม "ค้นเว็บ" ในแถวปุ่มของแชท โมเดลจะตัดสินเองว่าจะเรียก `web_search` เมื่อไร (Gemini/OpenRouter ใช้ tool calling จริง ส่วน Qwen ในเครื่องจะค้นให้หนึ่งครั้งแล้วนำผลใส่ prompt) ผลค้นหาจาก DuckDuckGo (ไม่ต้องใช้ API key) แสดงเป็นลิงก์แหล่งที่มาใต้คำตอบ คำค้นจะถูกส่งออกนอกองค์กร และเนื้อหาจากเว็บถือเป็นข้อมูลที่ไม่เชื่อถือ

## เชื่อมต่อบริการจริง

- [โมเดลและ LiteLLM](docs/model-configuration.md)
- [การติดตั้ง](docs/deployment.md)
- [สถาปัตยกรรมและการแยกข้อมูล](docs/architecture.md)
- [ผลทดสอบจริง](docs/verification.md)
- [ข้อจำกัดและงานที่ยังเหลือ](docs/limitations.md)

ภาพ วิดีโอ และเสียงมี provider adapters และงาน Celery ที่บันทึกสถานะ ผลลัพธ์ ประวัติ และดาวน์โหลดได้ ต้องตั้งค่า Gateway/API key และโมเดลจริงใน Super Admin ก่อนใช้งาน การทดสอบ adapters ใช้ผู้ให้บริการจำลองอย่างชัดเจน ยังไม่ได้ใช้ API แบบชำระเงินจริง

## ตรวจสอบ

```powershell
# ชุดทดสอบ backend ใช้ฐานข้อมูลแยกภายใต้ apps/api/data/tests
cd apps/api
../../.venv/Scripts/python.exe -m pytest -q
cd ../web
npm.cmd run typecheck
npm.cmd run test
npm.cmd run build
cd ../..
# ตรวจ integration ผ่าน PostgreSQL, S3, Qdrant และ Celery จริง
docker compose exec -T api python -m hub.integration_check
```

Integration check เพิ่ม PDF ตัวอย่างหนึ่งไฟล์และกิจกรรมทดสอบในองค์กรสาธิต ไม่ลบข้อมูลอื่น ผลการรันล่าสุดอยู่ในเอกสาร verification

## โครงสร้าง

```text
apps/web/              Next.js App Router, Thai UI, React Query, Recharts
apps/api/hub/          Domain modules, authentication, ingestion, retrieval, admin API
apps/api/migrations/   Alembic schema migrations
apps/api/tests/        API, tenant isolation, parser tests
infrastructure/docker/ Multi-stage non-root application images
scripts/               Setup and local startup
docs/                  Architecture, configuration, verification and limitations
compose.yaml           Development stack
compose.prod.yaml      Production-oriented baseline (ต้องตั้งค่าเพิ่มเติม)
```

ข้อมูลอยู่ใน named volumes การออกจากระบบยกเลิก session ในฐานข้อมูล ข้อมูลของแต่ละองค์กรตรวจ `tenant_id` ทาง API และใน Qdrant filter ขณะค้นหา พร้อมสิทธิ์ผู้ใช้/แผนก/กลุ่มระดับคลังและเอกสาร และบังคับซ้ำที่ฐานข้อมูลด้วย PostgreSQL row-level security (แอปรันด้วย role `hub_app`, migration/สำรองข้อมูลใช้ role เจ้าของ) ผู้ใช้และผู้ดูแลแผนกเห็นได้เฉพาะแถวขององค์กรตน

ส่วนสำรองข้อมูลและสถานะบริการอยู่ที่ `/super-admin/operations` มี ClamAV, คิวงานพร้อม recovery, แจ้งเตือนภายในระบบ และชุดสำรองเข้ารหัสทุก 24 ชั่วโมง เก็บ 7 ชุด กู้คืนจะสร้าง safety snapshot ก่อนแทนที่ฐานข้อมูลและสร้างดัชนีใหม่ เก็บ `.env`/คีย์เข้ารหัสแยกจาก backup และคัดลอกไฟล์สำรองออกนอกเครื่อง รายละเอียด: [คู่มือการปฏิบัติการ](docs/operations.md)

เว็บไซต์รันในเครื่องนี้ ไม่ได้เผยแพร่ขึ้นอินเทอร์เน็ต เนื่องจากสถาปัตยกรรม FastAPI/Celery และบริการ Docker ต้องใช้โฮสต์สำหรับ container หลายบริการ
