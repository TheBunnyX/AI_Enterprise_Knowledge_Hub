"""The ready-made AI skills: enough of them, valid, shared with everyone, and added without overwriting anyone's edits."""
from sqlalchemy import select
from conftest import login_as
from hub import sample_skills, seed
from hub.database import SessionLocal
from hub.skills import Skill, SkillInput


def add_samples():
    with SessionLocal() as db: return sample_skills.ensure(db)


def test_there_are_at_least_seven_distinct_samples_that_pass_the_skill_rules():
    assert len(sample_skills.SAMPLES) >= 7
    names = [s[1] for s in sample_skills.SAMPLES]
    assert len(set(names)) == len(names)
    for icon, name, description, use_documents, instructions in sample_skills.SAMPLES:
        SkillInput(name=name, description=description, instructions=instructions, icon=icon, use_documents=use_documents, shared=True)  # the same limits as the API
        assert len(instructions) >= 200, name  # substantial, not a one-liner


def test_everyone_in_the_organisation_sees_them_and_only_the_admin_owns_them(client):
    login_as(client, 'admin')
    assert add_samples() == len(sample_skills.SAMPLES)
    for role in ('member', 'department', 'admin'):
        login_as(client, role)
        listed = client.get('/api/skills').json()['skills']
        assert {s['name'] for s in listed} >= {s[1] for s in sample_skills.SAMPLES}
        assert all(s['shared'] for s in listed)
    login_as(client, 'member')
    one = client.get('/api/skills').json()['skills'][0]
    assert one['mine'] is False and client.put(f"/api/skills/{one['id']}", json={'name': 'x', 'instructions': 'คำสั่งยาวพอสมควรแล้ว'}).status_code in (403, 404)


def test_running_again_adds_nothing_and_never_overwrites_an_edit(client):
    login_as(client, 'admin')
    add_samples()
    with SessionLocal() as db:
        s = db.scalars(select(Skill)).first(); s.instructions = 'แก้ไขโดยผู้ดูแล ยาวพอสมควรแล้ว'; edited = s.id; db.commit()
    assert add_samples() == 0
    with SessionLocal() as db: assert db.get(Skill, edited).instructions == 'แก้ไขโดยผู้ดูแล ยาวพอสมควรแล้ว'
    with SessionLocal() as db:  # a deleted sample comes back, the others stay
        db.delete(db.get(Skill, edited)); db.commit()
    assert add_samples() == 1


def test_the_seed_adds_them_unless_switched_off(client, monkeypatch):
    with SessionLocal() as db: assert seed.ensure_sample_skills(db) == 0  # the test suite switches them off
    monkeypatch.setenv('SEED_SAMPLE_SKILLS', 'true')
    with SessionLocal() as db: assert seed.ensure_sample_skills(db) == len(sample_skills.SAMPLES)


def test_a_sample_skill_steers_the_chat_it_is_picked_in(client):
    login_as(client, 'admin'); add_samples()
    login_as(client, 'department')
    from hub.skills import prompt_for
    skill = next(s for s in client.get('/api/skills').json()['skills'] if s['name'] == 'Document comparison')
    with SessionLocal() as db:
        text = prompt_for(db.get(Skill, skill['id']))
    assert 'table' in text and 'Document comparison' in text and 'กฎความปลอดภัย' in text  # the safety rules stay above the skill


def test_the_samples_are_english_and_old_thai_ones_are_converted_in_place(client):
    import re
    for icon, name, description, use_documents, instructions in sample_skills.SAMPLES:
        assert not re.search(r'[฀-๿]', name + description + instructions), name
    login_as(client, 'admin')
    add_samples()
    with SessionLocal() as db:
        row = db.scalars(select(Skill).where(Skill.name == sample_skills.SAMPLES[0][1])).one()
        row.name = sample_skills.LEGACY[0]; row.instructions = 'คำสั่งเก่าภาษาไทย ยาวพอสมควรแล้ว'; old_id = row.id; db.commit()
    assert add_samples() == 0  # converted, not duplicated
    with SessionLocal() as db:
        row = db.get(Skill, old_id)
        assert row.name == sample_skills.SAMPLES[0][1] and row.instructions == sample_skills.SAMPLES[0][4]
