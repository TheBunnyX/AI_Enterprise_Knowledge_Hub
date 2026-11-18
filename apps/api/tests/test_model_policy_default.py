"""A model registered after an organisation's policy was saved: open policies stay open, narrowed ones stay narrow."""
from sqlalchemy import select
from conftest import login_as
from hub.database import SessionLocal
from hub.models import AIModel, Organization
from hub.feature_models import ModelPolicy


def tenant_id(client): return client.get('/api/auth/me').json()['tenant_id']


def new_model(admin, name):
    r = admin.post('/api/admin/models', json={'name': name, 'provider': 'LiteLLM', 'api_id': name, 'category': 'LLM', 'enabled': True, 'input_price': 0, 'output_price': 0})
    assert r.status_code == 201, r.text
    return r.json()['id']


def test_a_model_added_later_joins_a_policy_that_allowed_everything(admin):
    tenant = tenant_id(admin)
    with SessionLocal() as db:
        everything = list(db.scalars(select(AIModel.id)))
        db.add(ModelPolicy(tenant_id=tenant, allowed_models=everything, default_model=everything[0])); db.commit()
    added = new_model(admin, 'later-model')
    with SessionLocal() as db:
        assert added in db.scalar(select(ModelPolicy).where(ModelPolicy.tenant_id == tenant)).allowed_models
    assert added in {m['id'] for m in admin.get('/api/models').json() if m['enabled']}


def test_a_deliberately_narrow_policy_does_not_grow(admin):
    tenant = tenant_id(admin)
    new_model(admin, 'second-model')  # now there is more than the one model the policy lists
    with SessionLocal() as db:
        first = db.scalars(select(AIModel.id)).first()
        db.add(ModelPolicy(tenant_id=tenant, allowed_models=[first], default_model=first)); db.commit()
    added = new_model(admin, 'later-model')
    with SessionLocal() as db:
        assert db.scalar(select(ModelPolicy).where(ModelPolicy.tenant_id == tenant)).allowed_models == [first]


def test_the_default_model_of_the_policy_is_what_a_chat_without_a_choice_uses(admin):
    tenant = tenant_id(admin)
    with SessionLocal() as db:
        chosen = db.scalar(select(AIModel).where(AIModel.category == 'LLM'))
        everything = list(db.scalars(select(AIModel.id)))
        db.add(ModelPolicy(tenant_id=tenant, allowed_models=everything, default_model=chosen.id)); db.commit()
        from hub.models import User
        from hub.policies import choose_model
        u = db.scalar(select(User).where(User.tenant_id == tenant))
        assert choose_model(db, u, 'LLM').id == chosen.id
