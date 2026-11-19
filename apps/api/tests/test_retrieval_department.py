"""A user's own department's knowledge gets a gentle boost in a close call; nothing is hidden from anyone else."""
from hub import retrieval


def test_the_boost_is_a_gentle_multiplier():
    assert 1 < retrieval.DEPARTMENT_BOOST <= 1.5  # a nudge that cannot bury a clearly better passage elsewhere
