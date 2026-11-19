# การสำรองข้อมูล สิทธิ์ และงานประมวลผล

## ชุดสำรอง

Super Admin → สำรองและกู้คืน แสดงสถานะบริการ งาน และชุดสำรอง กด “สำรองตอนนี้” เพื่อสร้างชุดใหม่ หรือดาวน์โหลด `.akh` ที่เข้ารหัส AES-256-GCM

ค่าเริ่มต้นสำรองทุก 24 ชั่วโมงและเก็บ 7 ชุด กำหนดด้วย `BACKUP_INTERVAL_HOURS` / `BACKUP_RETENTION` ใน Compose environment ใช้ `BACKUP_ENCRYPTION_KEY` หรือ fallback `SECRETS_KEY` ต้องเก็บคีย์เดิมและไฟล์ตั้งค่าแยกไว้อย่างปลอดภัย การหมุนคีย์จะทำให้ชุดเก่าเปิดไม่ได้หากไม่มีคีย์เก่า

Backup ครอบคลุม PostgreSQL และไฟล์ใน S3 รวมเวอร์ชันเก่าและสื่อ ไม่รวม `.env`, TLS certificates หรือ Qdrant index ซึ่งสร้างใหม่จากเอกสารได้ Volume `backups-data` อยู่บนเครื่องเดียวกัน ต้องดาวน์โหลดหรือส่งสำเนาออกนอกเครื่องเพื่อรับมือเครื่องเสีย

ก่อนกู้คืน กด “ตรวจ / กู้คืน” ตรวจเวลาชุดสำรองและจำนวนไฟล์ พิมพ์ข้อความยืนยันของชุดนั้น ระบบหยุดการเขียนใหม่ รอไม่ให้มีงานหรือแชทกำลังทำงาน สร้าง safety snapshot แล้วจึงกู้คืนด้วย transaction เดียว หากมีงานค้างอยู่จะปฏิเสธการกู้คืน งานสื่อจากชุดสำรองไม่ส่งคำสั่งสร้างใหม่อัตโนมัติ หลังจบตรวจสถานะและเข้าสู่ระบบใหม่

ทดสอบกู้คืนแบบแยกโดย `docker compose exec -T api python -m hub.ops_integration_check` สร้างชุดสำรองปัจจุบัน กู้คืนลงฐาน PostgreSQL ชั่วคราวและ S3 prefix แยก ตรวจจำนวนเอกสาร/แฮชไฟล์ แล้วลบเฉพาะเป้าหมายทดสอบ ไม่แทนที่ฐานใช้งาน

## สิทธิ์และการแชร์

หน้าเอกสาร/คลังความรู้มีแผนก กลุ่ม และสมาชิก เลือกคลังหรือเอกสารเพื่อกำหนดอ่าน/เขียน เอกสารจำกัดสิทธิ์เพิ่มเติมจากคลัง ผู้รับต้องผ่านทั้งสองชั้น ผู้ดูแลและผู้จัดการความรู้เข้าถึงภายในองค์กรเพื่อบริหารได้เสมอ

หน้าแชทเลือก “แชร์ภายในองค์กร” กำหนดผู้ใช้/กลุ่มและวันหมดอายุ 1–90 วัน การแชร์เป็นอ่านอย่างเดียวและไม่เพิ่มสิทธิ์เอกสาร เมื่อสิทธิ์เอกสารอ้างอิงถูกถอน จะไม่เปิดบทสนทนานั้นให้ผู้รับ

## ตรวจไวรัสและกู้คืนงาน

ClamAV ตรวจไฟล์ก่อน parser/OCR/การจัดเก็บ หากบริการล่มจะปิดรับไฟล์ ต้องให้ ClamAV ดาวน์โหลด signature และพร้อมก่อนอัปโหลด ปฏิเสธไฟล์อันตรายพร้อมแจ้งผู้ดูแล ไม่จัดเก็บไฟล์นั้น

ระบบตรวจ lease งานทุก 60 วินาทีและลอง ingestion ใหม่ได้ไม่เกิน 5 ครั้ง งานสื่อที่สถานะไม่ชัดเจนจะขึ้น “ต้องตรวจสอบ” ต้องตรวจผลที่ผู้ให้บริการก่อนกดลองใหม่ เพราะอาจเกิดค่าบริการใหม่ วิดีโอที่มี provider job ID จะตรวจสถานะเดิมต่อ

กระดิ่งแสดงแจ้งเตือนตามสิทธิ์ พร้อมสถานะกลับมาปกติ ไม่ใช่ external monitoring: เมื่อฐานข้อมูล/API หรือทั้งเครื่องล่มจะเปิดหน้าแจ้งเตือนไม่ได้

PDF ต้นฉบับเปิดจากเอกสารหรืออ้างอิงในแชท ไฮไลต์ text layer ได้ หน้า scan ที่ไม่มี text layer แสดงต้นฉบับพร้อม OCR ในแท็บข้อความ ยังไม่มีไฮไลต์ตำแหน่ง OCR บนภาพ

## Deploy from GitHub with only env vars (Dokploy)

1. On the source machine: Admin → Backups → create a backup and download the `.akh` file. Host it at a private HTTPS URL
   (e.g. a private GitHub release asset or object storage with a token).
2. In Dokploy create a Compose app from the GitHub repo, files `compose.yaml` + `compose.prod.yaml`, and set env vars only:
   `POSTGRES_PASSWORD`, `SECRETS_KEY` (both identical to the source), `WEB_ORIGIN=https://ai.mongkhonhatit.com`,
   `WEB_BIND=192.168.1.12`, `SEED_BACKUP_URL`, `SEED_BACKUP_TOKEN` (optional), plus the provider keys from `.env`.
3. Deploy. On first start the API restores the snapshot into the empty database, rebuilds the search index, and writes
   `/data/.seed-restored` so it never runs again. Existing data is never overwritten.
4. Change the demo account passwords afterwards (`DEMO_ACCOUNTS` stays empty in production).
