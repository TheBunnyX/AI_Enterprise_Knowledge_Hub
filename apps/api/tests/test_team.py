from sqlalchemy import select
from hub.database import SessionLocal
from hub.models import User, Organization, Usage
from hub.ops_models import Group, GroupMember
from hub.auth import passwords

PW = 'testing-password-123'

def login(client, email, password=PW):
    client.post('/api/auth/logout')
    return client.post('/api/auth/login', json={'email': email, 'password': password})

def seed_people(tenant_id):
    """Department admin D in department X with member M1; outsider O (no department) and peer admin P in X."""
    with SessionLocal() as db:
        people = {}
        for key, role in (('d', 'DEPARTMENT_ADMIN'), ('m1', 'USER'), ('o', 'USER'), ('p', 'DEPARTMENT_ADMIN')):
            a = User(tenant_id=tenant_id, email=f'{key}@team.test', name=key, role=role, password_hash=passwords.hash(PW))
            db.add(a); db.flush(); people[key] = a.id
        x = Group(tenant_id=tenant_id, name='แผนก X', kind='department'); db.add(x); db.flush()
        for key in ('d', 'm1', 'p'): db.add(GroupMember(tenant_id=tenant_id, group_id=x.id, user_id=people[key]))
        db.add(Usage(tenant_id=tenant_id, user_id=people['m1'], model='m', input_tokens=10, output_tokens=5, cost=0.5))
        db.commit()
        people['dept'] = x.id
        return people

def tenant_of(email):
    with SessionLocal() as db: return db.scalar(select(User).where(User.email == email)).tenant_id

def test_member_cannot_use_team_endpoints(member):
    assert member.get('/api/team/users').status_code == 403
    assert member.post('/api/team/users', json={'name': 'x', 'email': 'x@team.test', 'password': PW}).status_code == 403

def test_department_admin_scope_and_usage(admin):
    t = tenant_of('admin@local.test'); p = seed_people(t)
    assert login(admin, 'd@team.test').status_code == 200
    rows = admin.get('/api/team/users').json()
    assert [r['email'] for r in rows] == ['m1@team.test']
    assert rows[0]['requests'] == 1 and rows[0]['input_tokens'] == 10 and rows[0]['departments'] == ['แผนก X']
    for target in (p['o'], p['p']):
        assert admin.post(f'/api/team/users/{target}/toggle').status_code == 404
        assert admin.post(f'/api/team/users/{target}/password', json={'password': PW + 'x'}).status_code == 404
        assert admin.put(f'/api/team/users/{target}', json={'name': 'z'}).status_code == 404

def test_department_admin_cannot_escalate_or_cross_tenant(admin, other_tenant):
    t = tenant_of('admin@local.test'); p = seed_people(t)
    login(admin, 'd@team.test')
    r = admin.post('/api/team/users', json={'name': 'N', 'email': 'n@team.test', 'password': PW, 'role': 'SUPER_ADMIN', 'tenant_id': other_tenant['org']})
    assert r.status_code == 201
    with SessionLocal() as db:
        n = db.scalar(select(User).where(User.email == 'n@team.test'))
        assert n.role == 'USER' and n.tenant_id == t
        assert db.scalar(select(GroupMember).where(GroupMember.user_id == n.id, GroupMember.group_id == p['dept']))
    assert 'n@team.test' in [x['email'] for x in admin.get('/api/team/users').json()]
    bad = admin.post('/api/team/users', json={'name': 'Q', 'email': 'q@team.test', 'password': PW, 'department_id': 'nope'})
    assert bad.status_code == 422
    assert admin.get('/api/team/users?tenant_id=' + other_tenant['org']).json() and all(x['tenant_id'] == t for x in admin.get('/api/team/users?tenant_id=' + other_tenant['org']).json())

def test_department_admin_disable_and_reset(admin):
    t = tenant_of('admin@local.test'); p = seed_people(t)
    login(admin, 'd@team.test')
    assert admin.post(f"/api/team/users/{p['m1']}/password", json={'password': 'short'}).status_code == 422
    assert admin.post(f"/api/team/users/{p['m1']}/password", json={'password': 'brand-new-password-1'}).status_code == 200
    assert admin.post(f"/api/team/users/{p['m1']}/toggle").json() == {'active': False}
    assert login(admin, 'm1@team.test', 'brand-new-password-1').status_code == 401
    login(admin, 'd@team.test')
    assert admin.post(f"/api/team/users/{p['m1']}/toggle").json() == {'active': True}
    assert login(admin, 'm1@team.test', 'brand-new-password-1').status_code == 200

def test_department_admin_without_department_sees_nobody(admin):
    t = tenant_of('admin@local.test')
    with SessionLocal() as db:
        db.add(User(tenant_id=t, email='lone@team.test', name='lone', role='DEPARTMENT_ADMIN', password_hash=passwords.hash(PW))); db.commit()
    login(admin, 'lone@team.test')
    assert admin.get('/api/team/users').json() == []

def test_super_admin_sees_all_and_can_create_in_any_tenant(admin, other_tenant):
    r = admin.get('/api/team/users').json()
    assert {x['tenant_id'] for x in r} >= {tenant_of('admin@local.test'), other_tenant['org']}
    assert admin.post('/api/team/users', json={'name': 'N', 'email': 'sa@team.test', 'password': PW, 'tenant_id': other_tenant['org']}).status_code == 422
    with SessionLocal() as db:
        g = Group(tenant_id=other_tenant['org'], name='ฝ่าย B', kind='department'); db.add(g); db.commit(); gid = g.id
    assert admin.post('/api/team/users', json={'name': 'N', 'email': 'sa@team.test', 'password': PW, 'tenant_id': other_tenant['org'], 'department_id': gid}).status_code == 201

def test_super_admin_manages_departments(admin):
    t = tenant_of('admin@local.test'); p = seed_people(t)
    names = [d['name'] for d in admin.get('/api/team/departments').json()]
    assert 'แผนก X' in names
    r = admin.post('/api/team/departments', json={'name': 'ฝ่ายการเงิน'}); assert r.status_code == 201
    fin = r.json()['id']
    assert admin.post('/api/team/departments', json={'name': 'ฝ่ายการเงิน'}).status_code == 409
    assert admin.put(f'/api/team/departments/{fin}', json={'name': 'ฝ่ายบัญชี'}).status_code == 200
    # candidates for Super Admin: any tenant user not already inside
    cands = {c['email'] for c in admin.get(f'/api/team/departments/{fin}/candidates').json()}
    assert 'o@team.test' in cands and 'd@team.test' in cands
    assert admin.post(f'/api/team/departments/{fin}/members', json={'user_id': p['o']}).status_code == 201
    assert admin.delete(f'/api/team/departments/{fin}').status_code == 409
    assert [u['email'] for u in admin.get(f'/api/team/users?department_id={fin}').json()] == ['o@team.test']
    # the only department of a user cannot be removed; add another first
    assert admin.delete(f"/api/team/departments/{fin}/members/{p['o']}").status_code == 409
    assert admin.post(f"/api/team/departments/{p['dept']}/members", json={'user_id': p['o']}).status_code == 201
    assert admin.delete(f"/api/team/departments/{fin}/members/{p['o']}").status_code == 200
    assert admin.delete(f'/api/team/departments/{fin}').status_code == 200

def test_department_admin_department_rules(admin):
    t = tenant_of('admin@local.test'); p = seed_people(t)
    with SessionLocal() as db:
        y = Group(tenant_id=t, name='แผนก Y', kind='department'); db.add(y); db.commit(); y_id = y.id
        db.add(User(tenant_id=t, email='y@team.test', name='y', role='USER', password_hash=passwords.hash(PW)))
        db.add(User(tenant_id=t, email='free@team.test', name='free', role='USER', password_hash=passwords.hash(PW))); db.commit()
    login(admin, 'd@team.test')
    assert [d['name'] for d in admin.get('/api/team/departments').json()] == ['แผนก X']
    assert admin.post('/api/team/departments', json={'name': 'new'}).status_code == 403
    assert admin.delete(f"/api/team/departments/{p['dept']}").status_code == 403
    assert admin.get(f'/api/team/users?department_id={y_id}').status_code == 404
    assert admin.post(f'/api/team/departments/{y_id}/members', json={'user_id': p['o']}).status_code == 404
    cands = {c['email'] for c in admin.get(f"/api/team/departments/{p['dept']}/candidates").json()}
    assert 'free@team.test' in cands and 'p@team.test' not in cands and 'm1@team.test' not in cands
    free = next(c['id'] for c in admin.get(f"/api/team/departments/{p['dept']}/candidates").json() if c['email'] == 'free@team.test')
    assert admin.post(f"/api/team/departments/{p['dept']}/members", json={'user_id': free}).status_code == 201
    assert admin.post(f"/api/team/departments/{p['dept']}/members", json={'user_id': p['p']}).status_code == 404
    assert admin.delete(f"/api/team/departments/{p['dept']}/members/{p['d']}").status_code == 400
    assert admin.delete(f"/api/team/departments/{p['dept']}/members/{p['p']}").status_code == 404
    assert admin.delete(f"/api/team/departments/{p['dept']}/members/{free}").status_code == 409  # only department

def test_user_quota_scope_and_enforcement(admin):
    t = tenant_of('admin@local.test'); p = seed_people(t)
    login(admin, 'd@team.test')
    assert admin.put(f"/api/team/users/{p['m1']}/quota", json={'monthly_budget': -1}).status_code == 422
    assert admin.put(f"/api/team/users/{p['o']}/quota", json={'monthly_budget': 5}).status_code == 404  # outside department
    assert admin.put(f"/api/team/users/{p['d']}/quota", json={'monthly_budget': 5}).status_code == 404  # not self
    assert admin.put(f"/api/team/users/{p['m1']}/quota", json={'monthly_budget': 0.5}).json() == {'monthly_budget': 0.5}
    row = admin.get('/api/team/users').json()[0]
    assert row['monthly_budget'] == 0.5 and row['month_spend'] == 0.5
    # m1 already used 1 this month (seeded Usage row), so chat is refused with the personal-quota message
    login(admin, 'm1@team.test')
    r = admin.post('/api/chat', json={'question': 'hello'})
    assert r.status_code == 429 and 'ของคุณ' in r.json()['detail']
    login(admin, 'd@team.test')
    assert admin.put(f"/api/team/users/{p['m1']}/quota", json={'monthly_budget': 0}).status_code == 200
    login(admin, 'm1@team.test')
    assert admin.post('/api/chat', json={'question': 'hello'}).status_code != 429
