"""Stops a small model that falls into a loop and repeats one passage until the token limit.

A reply that ends with the same block of text three times in a row is a loop: `trim` keeps one copy and tells the caller to stop reading.
"""
MIN_BLOCK = 30    # shorter repeats ("ha ha ha", table rules, "...") are normal text
MAX_BLOCK = 600


def trim(answer):
    """(text, True) when the end of `answer` is the same block three times: the text keeps a single copy. Otherwise (answer, False)."""
    n = len(answer)
    for size in range(MIN_BLOCK, min(MAX_BLOCK, n // 3) + 1):
        a, b, c = answer[n - 3 * size:n - 2 * size], answer[n - 2 * size:n - size], answer[n - size:]
        if a == b == c:
            return answer[:n - 2 * size], True
    return answer, False


class Watch:
    """Checks a growing answer every `step` characters, which keeps the cost of scanning small."""
    def __init__(self, step=120):
        self.step, self.checked = step, 0

    def looped(self, answer):
        if len(answer) - self.checked < self.step:
            return answer, False
        self.checked = len(answer)
        return trim(answer)
