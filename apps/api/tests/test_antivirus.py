

def test_env_master_switch_disables_scanning(monkeypatch):
    from hub import antivirus
    antivirus.forget()
    monkeypatch.setenv('CLAMAV_ENABLED', '0')
    assert not antivirus.enabled()
    assert antivirus.scan(b'anything') == 'disabled'
    antivirus.forget()  # leave no cached value for other tests
