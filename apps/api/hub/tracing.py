"""Optional Langfuse tracing of chat requests (self-hosted, see compose.langfuse.yaml).

Off unless LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY and LANGFUSE_HOST are all set. Nothing here may ever break a chat: every call
is wrapped, and a failure only logs a warning. One trace per chat request holds the retrieval step (which passages, with scores) and
the model call (model, token usage, cost), tagged with the pseudonymous user, the organisation and the conversation as the session.

LANGFUSE_CAPTURE_CONTENT=false keeps questions, passages and answers out of Langfuse (only metadata, scores and costs are sent).
"""
import hashlib
import logging
import os
import time

log = logging.getLogger(__name__)
_client = None


def enabled():
    return bool(os.getenv('LANGFUSE_PUBLIC_KEY') and os.getenv('LANGFUSE_SECRET_KEY') and os.getenv('LANGFUSE_HOST'))


def capture_content():
    return os.getenv('LANGFUSE_CAPTURE_CONTENT', 'true').strip().lower() != 'false'


def client():
    """The shared Langfuse client, created on first use; None when tracing is off or could not start."""
    global _client
    if _client is None and enabled():
        try:
            from langfuse import Langfuse
            _client = Langfuse(public_key=os.environ['LANGFUSE_PUBLIC_KEY'], secret_key=os.environ['LANGFUSE_SECRET_KEY'], host=os.environ['LANGFUSE_HOST'],
                               environment=os.getenv('LANGFUSE_ENVIRONMENT', 'default'), sample_rate=float(os.getenv('LANGFUSE_SAMPLE_RATE', '1')))
        except Exception:
            log.warning('Langfuse could not be started; tracing is off', exc_info=True)
            os.environ.pop('LANGFUSE_HOST', None)
    return _client


def shutdown():
    if _client is not None:
        try: _client.shutdown()
        except Exception: log.warning('Langfuse flush failed', exc_info=True)


def pseudonym(value):
    """Stable id for Langfuse that does not reveal the account id."""
    return hashlib.sha256(('hub:' + str(value)).encode()).hexdigest()[:24]


class ChatTrace:
    """Collects what happened during one chat request and sends it as one trace when finish() is called."""

    def __init__(self, *, question, user_id, tenant_id, conversation_id, found, knowledge_base_id=None, agent=False, web=False):
        self.started = time.time()
        self.question, self.user_id, self.tenant_id, self.conversation_id = question, user_id, tenant_id, conversation_id
        self.found, self.knowledge_base_id, self.agent, self.web = found, knowledge_base_id, agent, web
        self.active = enabled()

    def finish(self, *, answer, error, complete, model, messages, input_tokens, output_tokens, cost, estimated, cache_hit):
        if not self.active:
            return
        try:
            self._send(answer, error, complete, model, messages, input_tokens, output_tokens, cost, estimated, cache_hit)
        except Exception:
            log.warning('Langfuse trace failed', exc_info=True)

    def _send(self, answer, error, complete, model, messages, input_tokens, output_tokens, cost, estimated, cache_hit):
        lf = client()
        if lf is None:
            return
        from langfuse import propagate_attributes
        show = capture_content()
        metadata = {'tenant': self.tenant_id, 'knowledge_base_id': self.knowledge_base_id or '', 'agent': self.agent, 'web_search': self.web,
                    'cache_hit': cache_hit, 'complete': complete, 'latency_ms': int((time.time() - self.started) * 1000), 'sources': len(self.found)}
        with propagate_attributes(user_id=pseudonym(self.user_id), session_id=self.conversation_id, trace_name='chat', tags=['chat', 'agent' if self.agent else 'rag'], metadata={'tenant': self.tenant_id}):
            root = lf.start_observation(name='chat', as_type='span', input=self.question if show else '[hidden]', metadata=metadata)
            if self.found or not self.agent:
                retrieval = root.start_observation(name='retrieval', as_type='retriever', input=self.question if show else '[hidden]',
                                                   output=[{'document': r.get('name'), 'page': r.get('page'), 'score': r.get('score'), 'rerank_score': r.get('rerank_score'),
                                                            **({'text': r.get('snippet')} if show else {})} for r in self.found], metadata={'results': len(self.found)})
                retrieval.end()
            if not cache_hit and (input_tokens or output_tokens or complete):
                generation = root.start_observation(name='llm', as_type='generation', model=model.get('name'), input=messages if show else '[hidden]', output=answer if show else '[hidden]',
                                                    usage_details={'input': input_tokens, 'output': output_tokens}, cost_details={'total': float(cost or 0)},
                                                    metadata={'provider': model.get('provider'), 'api_id': model.get('api_id'), 'cost_estimated': estimated})
                generation.end()
            root.update(output=answer if show else '[hidden]', level='ERROR' if error else None, status_message=error or None)
            root.end()
