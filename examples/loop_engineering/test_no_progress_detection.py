from loop_engineering.no_progress_detection import ProgressMonitor

PATCH_A = "def total(xs):\n    return sum(xs)\n"
PATCH_B = "def total(xs):\n    return sum(x for x in xs if x is not None)\n"
PATCH_C = "def total(xs):\n    result = 0\n    for x in xs:\n        result += x\n    return result\n"


def run(outputs, scores=None, **kw):
    m = ProgressMonitor(**kw)
    states = [m.observe(o, (scores or [None] * len(outputs))[i]) for i, o in enumerate(outputs)]
    return m, states


def test_distinct_attempts_count_as_progress():
    _, states = run([PATCH_A, PATCH_B, PATCH_C])
    assert states == ["improving"] * 3


def test_identical_patch_repeated_is_a_plateau_after_patience():
    _, states = run([PATCH_A, PATCH_B, PATCH_B, PATCH_B])
    assert states == ["improving", "improving", "improving", "plateau"]  # one repeat is normal; two is a stall


def test_cosmetic_rewording_still_counts_as_the_same():
    _, states = run([PATCH_B, PATCH_B + " ", PATCH_B + "  "])
    assert states[-1] == "plateau"


def test_flip_flopping_between_two_patches_is_oscillation():
    _, states = run([PATCH_A, PATCH_B, PATCH_A, PATCH_B, PATCH_A])
    assert states[-1] == "oscillating"


def test_best_returns_highest_scoring_iteration_not_the_last():
    m, _ = run([PATCH_A, PATCH_B, PATCH_A, PATCH_B], scores=[0.4, 0.9, 0.4, 0.9 - 0.01])
    assert m.best() == PATCH_B


def test_score_drop_is_flagged_as_regressing():
    _, states = run([PATCH_A, PATCH_C], scores=[0.8, 0.5])
    assert states[-1] == "regressing"
