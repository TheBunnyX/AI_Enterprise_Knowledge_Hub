"""Departments and documents carry a Thai and an English name; both are editable and the file extension never changes."""
from conftest import login_as
from test_departments import as_super, make_kb, put


def test_a_department_keeps_both_names_and_they_can_be_edited(client):
    as_super(client)
    made = client.post('/api/team/departments', json={'name': 'ฝ่ายทดสอบสองภาษา', 'name_en': 'Bilingual Test Dept'})
    assert made.status_code == 201 and made.json()['name_en'] == 'Bilingual Test Dept'
    did = made.json()['id']
    assert client.put(f'/api/team/departments/{did}', json={'name': 'ฝ่ายทดสอบสองภาษา', 'name_en': 'Renamed Dept'}).status_code == 200
    row = next(d for d in client.get('/api/team/departments').json() if d['id'] == did)
    assert row['name'] == 'ฝ่ายทดสอบสองภาษา' and row['name_en'] == 'Renamed Dept'
    assert client.post('/api/team/departments', json={'name': 'ฝ่ายไม่มีอังกฤษ'}).json()['name_en'] == ''  # English name is optional


def test_a_document_has_an_editable_english_name_and_a_fixed_extension(client):
    as_super(client)
    kb = make_kb(client, 'สองภาษา')
    doc = put(client, kb, name='นโยบายลา.txt').json()
    listed = next(d for d in client.get('/api/documents').json() if d['id'] == doc['id'])
    assert listed['name'] == 'นโยบายลา.txt' and listed['name_en'] == ''
    r = client.put(f"/api/documents/{doc['id']}/names", json={'name_en': 'Leave Policy.txt'}); assert r.status_code == 200
    assert client.put(f"/api/documents/{doc['id']}/names", json={'name': 'นโยบายการลาใหม่.txt'}).json()['name'] == 'นโยบายการลาใหม่.txt'
    assert client.put(f"/api/documents/{doc['id']}/names", json={'name': 'x.pdf'}).status_code == 422  # the extension decides how it is read
    assert client.put(f"/api/documents/{doc['id']}/names", json={'name': '  '}).status_code in (422,)
    listed = next(d for d in client.get('/api/documents').json() if d['id'] == doc['id'])
    assert listed['name'] == 'นโยบายการลาใหม่.txt' and listed['name_en'] == 'Leave Policy.txt'
    assert client.put(f"/api/documents/{doc['id']}/names", json={'name': '../../etc/passwd.txt'}).json()['name'] == 'passwd.txt'  # a path is never kept


def test_search_results_carry_the_english_name(client):
    as_super(client)
    kb = make_kb(client, 'ค้นหาสองภาษา')
    doc = put(client, kb, text='เบี้ยเลี้ยงต่างจังหวัดวันละ 400 บาท', name='เบี้ยเลี้ยง.txt').json()
    client.put(f"/api/documents/{doc['id']}/names", json={'name_en': 'Allowance.txt'})
    from hub.database import SessionLocal
    from hub import retrieval
    from hub.models import User
    from sqlalchemy import select
    with SessionLocal() as db:
        admin = db.scalar(select(User).where(User.email == 'admin@local.test'))
        rows = retrieval.search(db, admin.tenant_id, 'เบี้ยเลี้ยงต่างจังหวัด', user=admin)
    assert any(r.get('name_en') == 'Allowance.txt' for r in rows)


def test_a_user_has_a_thai_and_an_english_name_that_can_be_edited(client):
    as_super(client)
    dept = client.post('/api/team/departments', json={'name': 'ฝ่ายชื่อผู้ใช้', 'name_en': 'Names Dept'}).json()['id']
    made = client.post('/api/team/users', json={'name': 'สมศรี ตัวอย่าง', 'name_en': 'Somsri Example', 'email': 'somsri@names.test', 'password': 'Correct-Horse-9!x', 'department_id': dept})
    assert made.status_code == 201, made.text
    row = next(a for a in client.get('/api/team/users').json() if a['email'] == 'somsri@names.test')
    assert row['name'] == 'สมศรี ตัวอย่าง' and row['name_en'] == 'Somsri Example' and row['departments_en'] == ['Names Dept']
    assert client.put(f"/api/team/users/{row['id']}", json={'name': 'สมศรี แก้ไข', 'name_en': 'Somsri Edited'}).status_code == 200
    row = next(a for a in client.get('/api/team/users').json() if a['id'] == row['id'])
    assert row['name'] == 'สมศรี แก้ไข' and row['name_en'] == 'Somsri Edited'
    assert 'name_en' in client.get('/api/auth/me').json()  # the signed-in user sees their own English name too


def test_a_knowledge_base_has_a_thai_and_an_english_name_that_can_be_edited(client):
    as_super(client)
    made = client.post('/api/knowledge-bases', json={'name': 'คลังทดสอบ', 'name_en': 'Test Library'})
    assert made.status_code == 201 and made.json()['name_en'] == 'Test Library'
    kid = made.json()['id']
    row = next(k for k in client.get('/api/knowledge-bases').json() if k['id'] == kid)
    assert row['name'] == 'คลังทดสอบ' and row['name_en'] == 'Test Library'
    assert client.put(f'/api/knowledge-bases/{kid}', json={'name': 'คลังทดสอบ', 'name_en': 'Renamed Library'}).status_code == 200
    assert client.put(f'/api/knowledge-bases/{kid}', json={'name': 'คลังทดสอบ'}).status_code == 200  # omitted = unchanged
    row = next(k for k in client.get('/api/knowledge-bases').json() if k['id'] == kid)
    assert row['name_en'] == 'Renamed Library'
    assert client.post('/api/knowledge-bases', json={'name': 'ไม่มีอังกฤษ'}).json()['name_en'] == ''
