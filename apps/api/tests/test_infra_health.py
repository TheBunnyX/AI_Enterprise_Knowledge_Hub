from hub import infra_health


def test_reports_six_services_and_marks_failures_down(monkeypatch):
    def boom():
        raise ConnectionError('down')

    monkeypatch.setattr(infra_health, '_cache', {'at': 0., 'data': None})
    monkeypatch.setitem(infra_health.PROBES, 'vector', boom)
    monkeypatch.setitem(infra_health.PROBES, 'queue', lambda: None)
    monkeypatch.setitem(infra_health.PROBES, 'storage', lambda: True)
    monkeypatch.setitem(infra_health.PROBES, 'antivirus', lambda: True)
    data = infra_health.check()
    up = {s['key']: s['up'] for s in data['services']}
    assert list(up) == ['api', 'database', 'storage', 'vector', 'queue', 'antivirus']
    assert up['api'] is True and up['vector'] is False and up['queue'] is None
    assert infra_health.check() is data  # cached within TTL


def test_slow_probe_counts_as_down_within_deadline(monkeypatch):
    import time
    monkeypatch.setattr(infra_health, '_cache', {'at': 0., 'data': None})
    monkeypatch.setattr(infra_health, 'TIMEOUT', 0.1)
    for k in infra_health.PROBES:
        monkeypatch.setitem(infra_health.PROBES, k, lambda: True)
    monkeypatch.setitem(infra_health.PROBES, 'vector', lambda: time.sleep(2) or True)
    t = time.monotonic()
    up = {s['key']: s['up'] for s in infra_health.check()['services']}
    assert time.monotonic() - t < 1 and up['vector'] is False and up['database'] is True


def test_endpoint_requires_login_and_returns_only_status(client):
    assert client.get('/api/system/health').status_code == 401
