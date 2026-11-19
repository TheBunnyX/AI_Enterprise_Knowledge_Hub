"""A Super Admin can switch virus scanning off for a deployment that does not run ClamAV."""
import pytest
from sqlalchemy import select
from conftest import login_as
from hub import antivirus
from hub.database import SessionLocal
from hub.feature_models import Setting
from hub.models import Audit
from test_platform import upload


def as_role(client, role): assert login_as(client, role).status_code == 200


def put(client, enabled): return client.put('/api/admin/antivirus', json={'enabled': enabled})


def audit_actions(client):
    as_role(client, 'admin')
    return [a['action'] for a in client.get('/api/audit').json()]


@pytest.fixture
def scanner_down(monkeypatch):
    """ClamAV is configured but nothing answers on its port, like a stopped container."""
    monkeypatch.setenv('CLAMAV_HOST', '127.0.0.1'); monkeypatch.setenv('CLAMAV_PORT', '1')


def test_scanning_is_on_by_default_and_only_a_super_admin_can_see_or_change_it(client):
    as_role(client, 'admin')
    assert client.get('/api/admin/antivirus').json() == {'enabled': True, 'configured': False, 'required': False}
    for role in ('department', 'member'):
        as_role(client, role)
        assert client.get('/api/admin/antivirus').status_code == 403 and put(client, False).status_code == 403
    assert antivirus.enabled() is True


def test_uploads_are_refused_while_the_scanner_is_down_and_accepted_once_scanning_is_off(client, scanner_down):
    as_role(client, 'department')
    assert upload(client).status_code == 503  # fails closed: an unscanned file is never stored
    as_role(client, 'admin'); assert put(client, False).json()['enabled'] is False
    as_role(client, 'department')
    assert upload(client).status_code == 201
    as_role(client, 'admin'); assert put(client, True).json()['enabled'] is True
    as_role(client, 'department'); assert upload(client, text='อีกไฟล์หนึ่ง สำหรับทดสอบ', name='again.txt').status_code == 503


def test_a_deployment_that_requires_a_scanner_but_has_none_can_opt_out(client, monkeypatch):
    monkeypatch.setenv('CLAMAV_REQUIRED', 'true')
    as_role(client, 'department')
    assert upload(client).status_code == 503
    as_role(client, 'admin')
    assert client.get('/api/admin/antivirus').json()['required'] is True
    put(client, False)
    as_role(client, 'department'); assert upload(client).status_code == 201


def test_scan_returns_disabled_without_touching_the_network(client, scanner_down, monkeypatch):
    import socket
    def no_network(*a, **k): raise AssertionError('the scanner must not be contacted')
    as_role(client, 'admin'); put(client, False)
    monkeypatch.setattr(socket, 'create_connection', no_network)
    assert antivirus.scan(b'anything') == 'disabled' and antivirus.ping() == {'status': 'disabled'}


def test_switching_is_audited_and_a_repeat_is_not(client):
    as_role(client, 'admin')
    put(client, False); put(client, False); put(client, True)
    actions = audit_actions(client)
    assert actions.count('ปิดการตรวจไวรัส') == 1 and actions.count('เปิดการตรวจไวรัส') == 1


def test_turning_it_off_raises_an_alert_that_turning_it_on_clears(client):
    from hub.ops_models import SystemAlert
    as_role(client, 'admin')
    put(client, False)
    with SessionLocal() as db: assert db.scalar(select(SystemAlert.status).where(SystemAlert.alert_key == 'antivirus-off')) == 'active'
    put(client, True)
    with SessionLocal() as db: assert db.scalar(select(SystemAlert.status).where(SystemAlert.alert_key == 'antivirus-off')) == 'resolved'


def test_health_checks_skip_a_scanner_that_was_switched_off(client, scanner_down, monkeypatch):
    from hub import infra_health, monitoring
    as_role(client, 'admin')
    put(client, False)
    assert infra_health._antivirus() is None  # shown as "not used", not as a red dot
    def boom(): raise AssertionError('a disabled scanner must not be pinged')
    monkeypatch.setattr(antivirus, 'ping', boom)
    assert 'antivirus' not in monitoring.probe()
    put(client, True)
    monkeypatch.setattr(antivirus, 'ping', lambda: (_ for _ in ()).throw(ConnectionError()))
    assert monitoring.probe()['antivirus'] == 'unavailable'  # back on: a down scanner is reported again


def test_other_processes_pick_the_change_up_and_an_unreadable_setting_means_on(client, monkeypatch):
    monkeypatch.setattr(antivirus, 'CACHE_SECONDS', 0)
    with SessionLocal() as db:
        db.add(Setting(key='antivirus', value={'enabled': False})); db.commit()  # written by another process
    assert antivirus.enabled() is False
    antivirus.forget()
    import hub.database
    monkeypatch.setattr(hub.database, 'SessionLocal', lambda: (_ for _ in ()).throw(RuntimeError('database down')))
    assert antivirus.enabled() is True  # nothing known: fail closed
