"""Check that the [n] markers in an answer point at the evidence that actually supports each statement.

Models often attach the wrong number (the sentence says "10 days" but cites the page that only mentions remote work).
For every statement followed by markers we score it against each retrieved passage and re-point the markers to the
passages that support it; markers no passage supports are dropped rather than left to mislead. Web results
(numbers after the document passages) and statements too short to judge are left alone.
"""
import re

GROUP = re.compile(r'[ \t]*(?:\[\d{1,3}\](?:[ \t]*[,，、][ \t]*)?){1,8}')
NUMBER = re.compile(r'\d+(?:[.,]\d+)?')
NOISE = re.compile(r'[\s\W_]+', re.UNICODE)
FLOOR = 0.15   # below this a passage does not support the statement
RELATIVE = 0.6  # keep passages scoring at least this fraction of the best one


def _grams(text, n=3):
    t = NOISE.sub('', text.lower())
    return {t[i:i + n] for i in range(len(t) - n + 1)}


def score(statement, passage):
    grams = _grams(statement)
    if not grams:
        return 0.0
    base = len(grams & _grams(passage)) / len(grams)
    nums = set(NUMBER.findall(statement))
    if nums:  # every figure in the statement should appear in the passage
        have = set(NUMBER.findall(passage))
        base -= 0.35 * len(nums - have) / len(nums)
        base += 0.15 * len(nums & have) / len(nums)
    return max(0.0, base)


def verify(answer, passages, total=None, judge=None):
    """passages: texts of the document citations in order ([1] is passages[0]). total: all numbered sources.

    judge(claims) may return, for each statement, the passage numbers that support it (one batched call, e.g. Gemini Decision 1);
    when it is missing or returns None the n-gram score below decides.
    """
    if not answer or not passages:
        return answer
    docs = len(passages)
    total = total or docs
    parts, claims, last = [], [], 0  # parts: text, or ('judge', index, numbers) for a marker group that needs a verdict
    for m in GROUP.finditer(answer):
        statement = answer[last:m.start()]
        parts.append(statement)
        last = m.end()
        nums = [n for n in (int(x) for x in re.findall(r'\[(\d{1,3})\]', m.group(0))) if 1 <= n <= total]
        if not nums:
            continue  # points at a source that does not exist
        if any(n > docs for n in nums):
            parts.append(' ' + ''.join(f'[{n}]' for n in dict.fromkeys(nums)))  # web sources: not verifiable here
            continue
        # the statement is the text since the previous marker group, limited to the current sentence
        claim = re.split(r'(?<=[.!?。])\s+|\n', statement)[-1].strip()
        if len(NOISE.sub('', claim)) < 6:
            parts.append(' ' + ''.join(f'[{n}]' for n in dict.fromkeys(nums)))
            continue
        parts.append(('judge', len(claims), claim))
        claims.append(claim)
    tail = answer[last:]
    verdicts = judge(claims) if judge and claims else None
    if verdicts is not None and len(verdicts) != len(claims):
        verdicts = None
    out = []
    for part in parts:
        if isinstance(part, str):
            out.append(part)
            continue
        _, index, claim = part
        if verdicts is not None:
            keep = [n for n in verdicts[index] if 1 <= n <= docs]
        else:
            scores = [score(claim, p) for p in passages]
            best = max(scores)
            keep = [i + 1 for i, s in sorted(enumerate(scores), key=lambda t: -t[1]) if best >= FLOOR and s >= max(FLOOR, best * RELATIVE)][:2]
        if keep:  # nothing supports it: do not cite
            out.append(' ' + ''.join(f'[{n}]' for n in sorted(keep)))
    out.append(tail)
    return re.sub(r' {2,}', ' ', ''.join(out))
