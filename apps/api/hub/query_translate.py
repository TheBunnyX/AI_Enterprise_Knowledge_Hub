"""Translate a question without Thai letters into a Thai search query, so it can find Thai passages.

Dense similarity between an English question and Thai text is weak (the e5-small model), so English questions over a Thai
knowledge base find the right passage less than half the time. One short call to the model the user chose turns the question
into Thai keywords first; the search then runs on that translation. The answer is still written for the original question.

The call is best effort: any failure, a timeout, or an empty answer returns '' and the search falls back to the original question.
"""
import os, re
from collections import OrderedDict
import httpx
from . import gateway

THAI_LETTERS = re.compile(r'[฀-๿]')
LATIN = re.compile(r'[A-Za-z]{2,}')
PROMPT = ('Translate the user question into Thai for searching Thai business documents (HR, finance, IT, safety, legal, customer service). '
          'Keep numbers, names and acronyms as they are. Answer with the Thai translation only, on one line. Do not answer the question.')
_CACHE = OrderedDict()   # question -> Thai query; small, per process
_CACHE_SIZE = 500


def enabled():
    return os.getenv('QUERY_TRANSLATION', 'true').lower() == 'true'


def needs_translation(question):
    """A question in Latin letters with no Thai: those are the ones that miss Thai passages."""
    q = question or ''
    return enabled() and not THAI_LETTERS.search(q) and bool(LATIN.search(q)) and len(q.split()) >= 2


def clean(text):
    """The model's reply as one plain line: no quotes, labels or extra lines; '' when it is not Thai."""
    line = (text or '').strip().splitlines()[0].strip() if (text or '').strip() else ''
    line = re.sub(r'^(?:Thai|คำแปล|แปล)\s*[:：]\s*', '', line, flags=re.I).strip(' "\'`“”')
    return line[:300] if THAI_LETTERS.search(line) else ''


LABEL = 'แปลคำค้น'  # usage label; the web UI shows it as "Query translation"


def usage_of(model, response):
    """Tokens and cost of the translation call: the provider's own cost when it reports one, otherwise the model's list price (an estimate)."""
    body = response.json(); u = body.get('usage') or {}
    tokens_in, tokens_out = int(u.get('prompt_tokens') or 0), int(u.get('completion_tokens') or 0)
    raw = response.headers.get('x-litellm-response-cost')
    reported = u.get('cost')
    try: cost = max(0.0, float(raw)) if raw is not None else (max(0.0, float(reported)) if isinstance(reported, (int, float)) else None)
    except ValueError: cost = None
    if cost is None: cost = (tokens_in * float(getattr(model, 'input_price', 0) or 0) + tokens_out * float(getattr(model, 'output_price', 0) or 0)) / 1e6
    return {'input_tokens': tokens_in, 'output_tokens': tokens_out, 'cost': cost, 'estimated': raw is None and not isinstance(reported, (int, float))}


async def translate(db, model, question, usage=None):
    """The Thai search query for `question`, or '' (not needed, not available, or the call failed). When `usage` is a list, the cost of the call (if one was made) is appended to it."""
    if not needs_translation(question): return ''
    key = question.strip().lower()
    if key in _CACHE:
        _CACHE.move_to_end(key); return _CACHE[key]
    try:
        url, secret = gateway.configuration(db, model.provider)
        if not url: return ''
        async with httpx.AsyncClient(timeout=httpx.Timeout(10, connect=4)) as client:
            r = await client.post(url + '/chat/completions', headers=gateway.headers(secret),
                                  json={'model': model.api_id, 'max_tokens': 160, 'temperature': 0,
                                        'messages': [{'role': 'system', 'content': PROMPT}, {'role': 'user', 'content': question[:600]}],
                                        **gateway.routing(model.provider, url)})
            r.raise_for_status()
            out = clean(r.json()['choices'][0]['message']['content'] or '')
            if usage is not None: usage.append(usage_of(model, r))
    except (httpx.HTTPError, KeyError, IndexError, ValueError, TypeError):
        return ''
    if out:
        _CACHE[key] = out
        while len(_CACHE) > _CACHE_SIZE: _CACHE.popitem(last=False)
    return out
