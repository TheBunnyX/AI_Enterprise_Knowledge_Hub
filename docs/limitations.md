# ข้อจำกัดปัจจุบัน

ฟีเจอร์หลักเพิ่มแล้วตาม [สถานะล่าสุด](feature-status.md) แต่ยังไม่ใช่การรับรองพร้อมใช้งาน Production ทุกข้อของ Master Prompt

- มี ACL รายผู้ใช้/แผนก/กลุ่ม/เอกสารใน API และ PostgreSQL row-level security แยกองค์กรแล้ว (ผู้ใช้/ผู้ดูแลแผนก) แต่ Super Admin และงานเบื้องหลังข้าม policy ได้ เพราะต้องทำงานข้ามองค์กร และ RLS ยังไม่แยกตามผู้ใช้/แผนกภายในองค์กร (ใช้ ACL ใน API)
- Docker สแกน ClamAV ก่อนอ่านหรือเก็บไฟล์ และปิดรับไฟล์เมื่อ scanner ล่ม ยังไม่มี parser sandbox isolation หรือ DLP
- LLM streaming/fallback, embeddings, reranker และสื่อทั้งสี่หมวดมี adapters แต่ยังไม่มี paid provider credentials สำหรับทดสอบจริง รองรับหลายผู้ให้บริการ (Google AI, OpenRouter, LiteLLM) แต่ละรายมี API key ของตัวเอง ยังไม่ได้ทดสอบกับ key จริง และไม่มีตัวจำกัด RPM/RPD ฝั่งเรา (พึ่งโมเดลสำรองเมื่อโดน 429)
- งบประมาณใช้ reported tokens/ราคาที่ผู้ดูแลกำหนด และราคา media ที่ upstream แจ้ง ค่าใช้จ่ายสื่อที่ไม่ทราบไม่ถูกนับเป็นยอดยืนยัน ไม่มี payment collection หรือการเทียบใบแจ้งหนี้
- โมเดลสำรองลองได้หนึ่งโมเดลที่ได้รับอนุญาตก่อนเริ่มส่งข้อความ ไม่มี full circuit breaker หรือ latency-based router
- การหยุดแชท/งานสื่อไม่รับประกันการหยุดคิดค่าบริการจาก provider งานบางชนิดอาจเสร็จที่ upstream แล้ว
- สำรองฐานข้อมูลและไฟล์แบบเข้ารหัสทุก 24 ชั่วโมง เก็บ 7 ชุดใน Docker volume บนเครื่องเดียวกัน ต้องดาวน์โหลด/คัดลอกออกนอกเครื่องและเก็บคีย์แยกเพื่อรับมือเครื่องเสีย ยังไม่มี offsite replication หรือกำหนดเวลา/retention ผ่านหน้าเว็บ
- กู้คืนทดสอบแล้วในฐาน PostgreSQL และพื้นที่ไฟล์แยก ไม่ได้กู้คืนทับฐานที่ผู้ใช้กำลังใช้งาน ดัชนี Qdrant สร้างใหม่หลัง live restore
- งาน ingestion มี lease/recovery และจำกัดการลองซ้ำ งานสื่อที่ไม่ทราบว่าผู้ให้บริการรับคำสั่งแล้วหรือยังต้องให้ผู้ดูแลตรวจและยืนยัน ไม่สามารถรับประกัน exactly-once ที่ผู้ให้บริการไม่รองรับ idempotency
- PDF มีไฮไลต์บนต้นฉบับสำหรับหน้าที่มีชั้นข้อความ หน้า PDF สแกนแสดงต้นฉบับและข้อความ OCR แยกแท็บ ยังไม่มี OCR bounding-box overlay
- การแจ้งเตือนอยู่ภายในระบบ หากฐานข้อมูล/API หรือเครื่องทั้งหมดล่มจะเปิดดูแจ้งเตือนไม่ได้ ต้องมี external monitoring เพิ่มสำหรับ production
- การค้นหาโหลด chunk ที่ได้รับอนุญาตใน memory เพื่อคำนวณ BM25 ต้องปรับสำหรับ corpus ขนาดใหญ่
- อ้างอิงเชื่อมกับหน้า/เวอร์ชันที่จัดเก็บจริง แต่ยังไม่ได้พิสูจน์ความถูกต้องของทุกข้อกล่าวอ้างจากโมเดลจริง
- Session sign-in rate limit เป็น process-local; production ต้องใช้ distributed controls, CSP, secret manager และ network segmentation
- ยังไม่มี HA, infrastructure resource monitoring, OpenTelemetry, Ragas/DeepEval หรือ evaluation dashboard
- Initial migration อ้างถึง metadata ปัจจุบัน ต้อง freeze definitions ก่อนใช้ schema history ใน Production ระยะยาว

ข้อมูลพัฒนายังคงอยู่ใน Docker named volumes และบริการเว็บผูก loopback ที่พอร์ต 3009 โดยไม่ได้เผยแพร่สู่สาธารณะ
- มี 3 บทบาท: Super Admin (ทั้งระบบ), ผู้ดูแลแผนก (DEPARTMENT_ADMIN) และผู้ใช้ (USER) ผู้ดูแลแผนกเห็นและจัดการได้ตาม ACL/กลุ่มที่ตนเป็นสมาชิก และแก้สมาชิกได้เฉพาะแผนก/กลุ่มของตน ยังไม่มีการผูกคลังความรู้กับแผนกแบบเจ้าของโดยตรง และ KB ที่เปิดให้ทั้งองค์กรยังเขียนได้ทุกบทบาท ไม่มีบทบาทอ่านอย่างเดียว
- โหมดทดสอบแบบระบบจริง (`DEMO_MODE=false`, ไม่ตั้ง `APP_ENV=production`): ไม่มีปุ่มเข้าสู่ระบบโดยไม่ใช้รหัสผ่าน ไม่ seed ข้อมูลตัวอย่าง และ `extractive-demo` ถูกปิด รหัสผ่านบัญชีทดสอบ 3 บัญชีอยู่ที่ `/data/test-accounts.txt` ใน API container การใช้งานจริงต้องใช้ `compose.prod.yaml` ที่ต้องมี HTTPS และ SSO
