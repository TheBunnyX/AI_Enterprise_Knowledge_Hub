"""Answer-quality gate with DeepEval: is the answer grounded, and do its [n] citations point at passages that support it?

Reads the rows written by `python -m eval.answers --dump FILE` (question, the passages the real search returned, the answer a
model wrote from them) and lets an LLM judge score each row:

  faithfulness       share of the answer's claims that the retrieved passages support (hallucination check)   [DeepEval]
  citation_accuracy  every [n] marker points at the n-th passage AND that passage supports the sentence       [DeepEval GEval]
  answer_has_fact    the expected phrase appears word for word in the answer (free, no judge)                 [exact check]

It runs in its own environment because DeepEval pins many packages the app does not use (see eval/requirements-deepeval.txt):

    uv venv .venv-eval && uv pip install --python .venv-eval/bin/python -r apps/api/eval/requirements-deepeval.txt
    make eval-deepeval                                  # 12 questions, Gemini flash-lite judge from GOOGLE_AI_API_KEY in .env
    make eval-deepeval ARGS="--min-faithfulness 0.8 --min-citation 0.7"      # exit code 1 when a mean falls below the bar

THIS CALLS A PAID/RATE-LIMITED API (the questions and the eval/corpus passages are sent to the judge provider). Use the
sample corpus, never real company documents, unless the judge is a model you host. DeepEval's usage telemetry is switched
off here. A small judge model can score Thai text unreliably: spot-check a few rows by hand before trusting a trend.
"""
import os
os.environ.setdefault('DEEPEVAL_TELEMETRY_OPT_OUT', 'YES')  # must be set before deepeval is imported
os.environ.setdefault('DEEPEVAL_UPDATE_WARNING_OPT_IN', 'NO')
import argparse, asyncio, json, re, sys, time, warnings
from pathlib import Path
import httpx

warnings.simplefilter('ignore', DeprecationWarning)
ROOT = Path(__file__).resolve().parents[3]


def judge_settings():
    env = {}
    env_file = ROOT / '.env'
    if env_file.exists(): env = dict(line.strip().split('=', 1) for line in env_file.read_text(encoding='utf-8').splitlines() if '=' in line and not line.startswith('#'))
    url = os.getenv('EVAL_JUDGE_URL', 'https://generativelanguage.googleapis.com/v1beta/openai').rstrip('/')
    key = os.getenv('EVAL_JUDGE_KEY') or env.get('GOOGLE_AI_API_KEY', '')
    if not key: raise SystemExit('Set EVAL_JUDGE_KEY (or GOOGLE_AI_API_KEY in .env) for the judge model')
    return url, key, os.getenv('EVAL_JUDGE_MODEL', 'gemini-3.1-flash-lite')


def squash(text): return re.sub(r'\s+', '', text)


def first_json(text):
    """The judge is asked for bare JSON; tolerate code fences and a sentence before or after it."""
    text = re.sub(r'^```(?:json)?|```$', '', text.strip(), flags=re.M).strip()
    start, end = text.find('{'), text.rfind('}')
    if start < 0 or end < start: raise ValueError('the judge returned no JSON object')
    return text[start:end + 1]


from deepeval.models import DeepEvalBaseLLM


class Judge(DeepEvalBaseLLM):
    """Any OpenAI-compatible chat endpoint (Google AI, OpenRouter, a local server) as DeepEval's judge."""

    def __init__(self, url, key, model):
        self.url, self.key, self.model_id = url, key, model
        super().__init__(model)

    def load_model(self): return httpx.Client(timeout=120)

    def get_model_name(self): return self.model_id

    def supports_json_mode(self): return False  # the schema is described in the prompt instead

    def generate(self, prompt, schema=None, **kwargs):
        if schema is not None:
            prompt += '\n\nReturn ONLY one JSON object that matches this JSON schema. No prose, no code fences.\n' + json.dumps(schema.model_json_schema(), ensure_ascii=False)
        body = {'model': self.model_id, 'temperature': 0, 'max_tokens': 2048, 'messages': [{'role': 'user', 'content': prompt}]}
        for attempt in range(6):
            try: r = self.model.post(self.url + '/chat/completions', headers={'Authorization': 'Bearer ' + self.key}, json=body)
            except httpx.TransportError:
                if attempt == 5: raise
                time.sleep(4 * (attempt + 1)); continue
            if r.status_code in (429, 500, 502, 503, 504) and attempt < 5: time.sleep(4 * (attempt + 1)); continue
            r.raise_for_status(); break
        text = r.json()['choices'][0]['message']['content'] or ''
        return schema.model_validate_json(first_json(text)) if schema is not None else text

    async def a_generate(self, prompt, schema=None, **kwargs): return await asyncio.to_thread(self.generate, prompt, schema)


CITATION_CRITERIA = (
    'The actual output answers a question using numbered passages. The retrieval context lists those passages, each starting with its number in square brackets. '
    'Judge the citations: (1) every factual statement carries a [n] marker; (2) each marker names a passage that exists; (3) the passage with that number really supports the statement it follows. '
    'Give a high score only when all three hold. Give a low score for statements without a marker, markers that point at a passage which does not support the statement, or numbers that do not exist. '
    'If the output honestly says the evidence is insufficient and makes no unsupported claim, give a high score.'
)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('rows', help='file written by: python -m eval.answers --dump FILE')
    parser.add_argument('--no-citation', action='store_true', help='skip the citation metric (saves about a third of the judge calls)')
    parser.add_argument('--min-faithfulness', type=float, help='exit with code 1 when the mean faithfulness is below this')
    parser.add_argument('--min-citation', type=float, help='exit with code 1 when the mean citation_accuracy is below this')
    parser.add_argument('--delay', type=float, default=0, help='seconds to wait between questions (free-tier rate limits)')
    parser.add_argument('--workers', type=int, default=6, help='questions judged at the same time (lower it when the provider rate-limits)')
    parser.add_argument('--json', help='write the per-question scores to this file')
    args = parser.parse_args()
    data = json.loads(Path(args.rows).read_text(encoding='utf-8'))
    rows = data['rows']
    url, key, model = judge_settings()
    from deepeval.metrics import FaithfulnessMetric, GEval
    from deepeval.test_case import LLMTestCase, SingleTurnParams
    judge = Judge(url, key, model)

    def score_row(row):
        """One question. Metrics hold their last score, so every call builds its own (this is what lets rows run in parallel)."""
        faithfulness = FaithfulnessMetric(threshold=0.7, model=judge, include_reason=False, async_mode=False)
        citation = GEval(name='citation_accuracy', criteria=CITATION_CRITERIA, evaluation_params=[SingleTurnParams.INPUT, SingleTurnParams.ACTUAL_OUTPUT, SingleTurnParams.RETRIEVAL_CONTEXT], model=judge, threshold=0.6, async_mode=False)
        out = {'question': row['user_input'], 'answer': row['response'], 'answer_has_fact': float(squash(row['reference']) in squash(row['response'])), 'faithfulness': None, 'citation_accuracy': None, 'errors': []}
        plain = LLMTestCase(input=row['user_input'], actual_output=row['response'], retrieval_context=row['retrieved_contexts'])
        numbered = LLMTestCase(input=row['user_input'], actual_output=row['response'], retrieval_context=[f'[{i}] {c}' for i, c in enumerate(row['retrieved_contexts'], 1)])
        for name, metric, case in [('faithfulness', faithfulness, plain)] + ([] if args.no_citation else [('citation_accuracy', citation, numbered)]):
            try: metric.measure(case, _show_indicator=False); out[name] = float(metric.score)
            except Exception as e: out['errors'].append(f'{name}: {type(e).__name__}: {str(e)[:160]}')  # one bad judge reply must not end the run
        if args.delay: time.sleep(args.delay)
        return out

    from concurrent.futures import ThreadPoolExecutor
    done = 0
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = [pool.submit(score_row, row) for row in rows]
        results = []
        for future in futures:  # in question order; they finish in any order
            results.append(future.result()); done += 1; print(f'judged {done}/{len(rows)}', end='\r', flush=True)
    print(f"judge: {model} | answers written by {data.get('answer_model')} | {len(rows)} questions" + ' ' * 20)
    means = {}
    for name in ('faithfulness', 'citation_accuracy', 'answer_has_fact'):
        scored = [r[name] for r in results if r[name] is not None]
        if scored: means[name] = sum(scored) / len(scored); print(f'{name:<20}{means[name]:>7.3f}   ({len(scored)}/{len(results)} scored)')
        elif name != 'citation_accuracy' or not args.no_citation: print(f'{name:<20}  no scores')
    weak = [r for r in results if any(r[n] is not None and r[n] < 0.5 for n in ('faithfulness', 'citation_accuracy'))]
    for r in weak[:5]: print(f"  low: {r['question'][:70]}  faithfulness={r['faithfulness']} citation={r['citation_accuracy']}")
    for r in results:
        for e in r['errors'][:1]: print('  error:', e)
    if args.json: Path(args.json).write_text(json.dumps({'judge': model, 'means': means, 'rows': results}, ensure_ascii=False, indent=1), encoding='utf-8')
    failed = [(n, means.get(n), bar) for n, bar in (('faithfulness', args.min_faithfulness), ('citation_accuracy', args.min_citation)) if bar is not None and (means.get(n) is None or means[n] < bar)]
    for n, got, bar in failed: print(f'FAIL {n}: {got if got is None else round(got, 3)} is below the bar {bar}')
    sys.exit(1 if failed else 0)


if __name__ == '__main__':
    main()
