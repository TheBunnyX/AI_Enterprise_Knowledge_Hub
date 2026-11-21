"""Langfuse tracing of chat: off by default, never breaks a chat, and respects the no-content setting."""
import pytest
from conftest import login_as
from hub import tracing
from test_platform import upload


class FakeObservation:
    def __init__(self, sink, kind, kwargs):
        self.sink, self.kind, self.kwargs = sink, kind, kwargs
        sink.append(self)

    def start_observation(self, **kwargs):
        return FakeObservation(self.sink, kwargs.get('as_type', 'span'), kwargs)

    def update(self, **kwargs):
        self.kwargs = {**self.kwargs, **kwargs}

    def end(self):
        self.kwargs['ended'] = True


class FakeLangfuse:
    def __init__(self):
        self.observations = []

    def start_observation(self, **kwargs):
        return FakeObservation(self.observations, kwargs.get('as_type', 'span'), kwargs)


@pytest.fixture
def langfuse(monkeypatch):
    fake = FakeLangfuse()
    monkeypatch.setenv('LANGFUSE_PUBLIC_KEY', 'pk-test')
    monkeypatch.setenv('LANGFUSE_SECRET_KEY', 'sk-test')
    monkeypatch.setenv('LANGFUSE_HOST', 'http://langfuse.test')
    monkeypatch.setattr(tracing, 'client', lambda: fake)
    return fake


def ask(client, question='ลาพักร้อนได้กี่วัน'):
    assert upload(client).status_code == 201  # only department admins may upload
    r = client.post('/api/chat', json={'question': question})
    assert r.status_code == 200
    return r


def test_tracing_is_off_without_keys(monkeypatch):
    for key in ('LANGFUSE_PUBLIC_KEY', 'LANGFUSE_SECRET_KEY', 'LANGFUSE_HOST'):
        monkeypatch.delenv(key, raising=False)
    assert not tracing.enabled()
    monkeypatch.setenv('LANGFUSE_PUBLIC_KEY', 'pk')
    assert not tracing.enabled()  # all three are needed


def test_master_switch_turns_tracing_off(monkeypatch):
    for key, value in (('LANGFUSE_PUBLIC_KEY', 'pk'), ('LANGFUSE_SECRET_KEY', 'sk'), ('LANGFUSE_HOST', 'http://x')):
        monkeypatch.setenv(key, value)
    monkeypatch.setenv('LANGFUSE_ENABLED', 'true')
    assert tracing.enabled()
    monkeypatch.setenv('LANGFUSE_ENABLED', 'false')
    assert not tracing.enabled()  # keys present, switch off


def test_chat_sends_one_trace_with_retrieval_and_generation(department, langfuse):
    ask(department)
    kinds = [o.kind for o in langfuse.observations]
    assert kinds == ['span', 'retriever', 'generation']
    root, retrieval, generation = langfuse.observations
    assert root.kwargs['input'] == 'ลาพักร้อนได้กี่วัน' and root.kwargs['ended']
    assert 'test.txt' in [hit['document'] for hit in retrieval.kwargs['output']]  # sample data may rank above it
    assert all('text' in hit for hit in retrieval.kwargs['output'])
    assert generation.kwargs['usage_details'] == {'input': 10, 'output': 5}
    assert generation.kwargs['model'] and generation.kwargs['input'] and generation.kwargs['output']


def test_content_can_be_kept_out_of_langfuse(department, langfuse, monkeypatch):
    monkeypatch.setenv('LANGFUSE_CAPTURE_CONTENT', 'false')
    ask(department)
    text = str([o.kwargs for o in langfuse.observations])
    assert 'ลาพักร้อนได้กี่วัน' not in text and 'พนักงานลาได้สิบวัน' not in text  # neither the question nor the passages
    assert langfuse.observations[2].kwargs['usage_details'] == {'input': 10, 'output': 5}  # numbers still reported


def test_user_is_pseudonymised():
    assert tracing.pseudonym('user-1') == tracing.pseudonym('user-1') != tracing.pseudonym('user-2')
    assert 'user-1' not in tracing.pseudonym('user-1')


def test_a_failing_langfuse_never_breaks_the_chat(department, monkeypatch):
    class Broken:
        def start_observation(self, **kwargs):
            raise RuntimeError('langfuse is down')
    monkeypatch.setenv('LANGFUSE_PUBLIC_KEY', 'pk')
    monkeypatch.setenv('LANGFUSE_SECRET_KEY', 'sk')
    monkeypatch.setenv('LANGFUSE_HOST', 'http://langfuse.test')
    monkeypatch.setattr(tracing, 'client', lambda: Broken())
    r = ask(department)
    assert '"type": "done"' in r.text or '"type":"done"' in r.text
