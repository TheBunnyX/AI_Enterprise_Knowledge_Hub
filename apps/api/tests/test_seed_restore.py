from pathlib import Path
from hub import seed_restore as seed

def test_seed_skips_without_url(monkeypatch):
    monkeypatch.delenv('SEED_BACKUP_URL',raising=False)
    assert seed.run()=='skipped'

def test_seed_skips_with_marker(monkeypatch,tmp_path):
    monkeypatch.setenv('SEED_BACKUP_URL','https://x.invalid/a.akh');monkeypatch.setenv('DATA_DIR',str(tmp_path))
    (tmp_path/'.seed-restored').write_text('x')
    assert seed.run()=='skipped'
