"""Decision models (typed yes/no, choice and score questions answered with calibrated probabilities): gemini-decision-1 on Google AI Studio's
Decisions API, and typesafe/jev-1.13, typesafe/jev-1.14, perplexity/pplx-decider-v1.2 (any "vendor/name" id) on OpenRouter's Decisions API.
DECISIONS_MODEL picks one; an id without "/" goes to Google AI, an id with "/" goes to OpenRouter.

Used for three small judgements: does the evidence answer the question, which passage supports each cited statement, and which
knowledge base suits a document. Off by default (DECISIONS_ENABLED=true turns it on; it needs GOOGLE_AI_API_KEY or a saved Google AI key).
Everything returns None when the service is off, fails or is slow, and the callers then use the older local method, so chat never depends on it.
Privacy: the question and the passages are sent to Google AI while it is on.
"""
import logging, os, time
import httpx
from . import gateway

URL = 'https://generativelanguage.googleapis.com/v1beta/decisions'
OPENROUTER_URL = 'https://openrouter.ai/api/alpha/decisions'  # alpha: the shape may change
MODELS = ('gemini-decision-1', 'typesafe/jev-1.14', 'typesafe/jev-1.13', 'perplexity/pplx-decider-v1.2')
log = logging.getLogger('hub.decisions')
BACKOFF_SECONDS = 120
MAX_PASSAGE_CHARS = 1500
_failed_at = [0.0]


def enabled():
    if os.getenv('DECISIONS_ENABLED', 'false').strip().lower() not in ('1', 'true', 'yes', 'on'):
        return False
    return time.monotonic() - _failed_at[0] > BACKOFF_SECONDS  # after a failure, use the local method for a while instead of waiting on a timeout each time


def model():
    return os.getenv('DECISIONS_MODEL', 'gemini-decision-1').strip() or 'gemini-decision-1'


def relevance_min():
    return float(os.getenv('DECISIONS_RELEVANCE_MIN', '0.25'))


def openrouter():
    return '/' in model()


def _key():
    """The provider's own key (.env or saved on the web page). The main gateway key is never sent to Google or OpenRouter."""
    provider = 'OpenRouter' if openrouter() else 'Google AI'
    try:
        if gateway.env_key(provider):
            return gateway.env_key(provider)
        from .database import SessionLocal
        with SessionLocal() as db:
            if (gateway.provider_settings(db).get(provider) or {}).get('encrypted_key'):
                return gateway.configuration(db, provider)[1]
    except Exception:
        pass
    return ''


def _request(text, questions):
    """(url, headers, body) in the dialect of the chosen model: Google calls the shared text `input`, OpenRouter `state`, and the two name the yes/no descriptions differently."""
    key = _key()
    if not openrouter():
        return URL, {'x-goog-api-key': key, 'Content-Type': 'application/json'}, {'model': model(), 'input': text, 'questions': questions}
    adapted = {}
    for name, q in questions.items():
        q = dict(q)
        if q['type'] == 'noul' and 'criteria' in q:
            q['criteria'] = {'true': q['criteria']['true_description'], 'false': q['criteria']['false_description']}
        adapted[name] = q
    return OPENROUTER_URL, {'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'}, {'model': model(), 'state': text, 'questions': adapted}


def ask(text, questions):
    """The `answers` map of a Decisions call, or None when off or failed. `text` is the shared input, `questions` the typed question map."""
    if not enabled():
        return None
    if not _key():
        return None
    try:
        url, headers, body = _request(text, questions)
        r = httpx.post(url, headers=headers, timeout=float(os.getenv('DECISIONS_TIMEOUT', '12')), json=body)
        if r.status_code == 400 and r.json().get('error', {}).get('code') in ('safety', 'prohibited_content', 'blocklist', 'content_blocked'):
            return None  # this one input was blocked: not a service failure, the local method answers
        r.raise_for_status()
        answers = r.json()['answers']
        if any(a.get('type') == 'refusal' for a in answers.values()):
            return None  # the model declined this input; the local method answers
        return answers
    except Exception as e:
        _failed_at[0] = time.monotonic()
        log.warning('Decisions call to %s failed, using the local method for %ss: %s', model(), BACKOFF_SECONDS, repr(e)[:200])
        return None


def _passages(passages):
    return '\n\n'.join(f'[{i + 1}]\n{p[:MAX_PASSAGE_CHARS]}' for i, p in enumerate(passages))


def relevant(question, passages):
    """Probability (0..1) that the passages answer the question, or None to keep the local rules."""
    if not question or not passages:
        return None
    answers = ask(f'Question:\n{question}\n\nEvidence:\n{_passages(passages)}', {'answers_it': {
        'type': 'noul',
        'instructions': 'Does the evidence contain the information needed to answer the question directly? A greeting, a test word, a calculation or an unrelated topic is not answered by the evidence.',
        'criteria': {'true_description': 'The evidence states the answer, or the facts needed for it.', 'false_description': 'The evidence is unrelated, or only shares a few words with the question.'}}})
    try:
        return float(answers['answers_it']['noul']) if answers else None
    except (KeyError, TypeError, ValueError):
        return None


def support(claims, passages, keep=0.3, limit=40):
    """For each statement: the numbers (1-based) of the passages that support it ([] = none does), or None for the whole call when unavailable."""
    if not claims or not passages or len(claims) > limit:
        return None
    options = {f'p{i + 1:03d}': f'Passage [{i + 1}]' for i in range(len(passages))} | {'none': 'No passage supports the statement.'}
    answers = ask(_passages(passages), {f'c{i}': {'type': 'choice', 'criteria': options,
                  'instructions': f'Which passage states the same fact as this statement (same figures, names and conditions)? Statement: {c}'} for i, c in enumerate(claims)})
    if not answers:
        return None
    out = []
    try:
        for i in range(len(claims)):
            probs = answers[f'c{i}']['probabilities']
            ranked = sorted(((p, k) for k, p in probs.items() if k != 'none'), reverse=True)
            if probs.get('none', 0) >= ranked[0][0]:
                out.append([]); continue
            out.append(sorted(int(k[1:]) for p, k in ranked[:2] if p >= keep))
    except (KeyError, TypeError, ValueError, IndexError):
        return None
    return out


def suggest_library(text, libraries):
    """(library id, confidence) that best fits a document among {id: description}, or None."""
    if not text or len(libraries) < 2:
        return None
    ids = list(libraries)
    keys = {f'k{i:03d}': ids[i] for i in range(len(ids))}
    answers = ask(text[:12000], {'library': {'type': 'choice', 'instructions': 'Which knowledge library should this document be filed in?',
                  'criteria': {k: libraries[v] for k, v in keys.items()}}})
    try:
        a = answers['library']
        return keys[a['choice']], float(a['confidence'])
    except (KeyError, TypeError, ValueError):
        return None
