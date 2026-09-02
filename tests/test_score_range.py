from pathlib import Path

from problemtools.checks.testdata import _check_score_range
from problemtools.model.testdata import TestCase, TestDataGroup

# Not test classes -- just named that way by the model. Tell pytest not to collect them.
TestCase.__test__ = False
TestDataGroup.__test__ = False

INF = float('inf')


def make_testcase(name: str) -> TestCase:
    path = Path(name)
    return TestCase(
        infile=path.with_suffix('.in'),
        ansfile=path.with_suffix('.ans'),
        path=path,
        input_validator_flags=[],
        output_validator_flags=[],
    )


def make_group(
    name: str,
    items: list[TestCase | TestDataGroup],
    grader_flags: str = '',
    grading: str = 'default',
    range_: str = '-inf +inf',
    accept_score: float = 1.0,
    reject_score: float = 0.0,
    on_reject: str = 'continue',
    is_root: bool = False,
) -> TestDataGroup:
    return TestDataGroup(
        name=name,
        datadir=Path(name),
        config={
            'grading': grading,
            'grader_flags': grader_flags,
            'range': range_,
            'accept_score': accept_score,
            'reject_score': reject_score,
            'on_reject': on_reject,
        },
        is_root=is_root,
        items=items,
    )


def test_group_sum_is_default_aggregator(diag):
    group = make_group(
        'g', [make_testcase('a'), make_testcase('b'), make_testcase('c')], range_='0 30', accept_score=10, reject_score=0
    )
    assert _check_score_range(group, False, diag) == (0, 30)
    assert diag.messages == []


def test_group_avg_aggregator(diag):
    group = make_group('g', [make_testcase('a')], grader_flags='avg', accept_score=10, reject_score=0)
    assert _check_score_range(group, False, diag) == (0, 10)


def test_avg_aggregator_with_on_reject_break_widens_range(diag):
    # subA (graded first) has a much wider range than subB. With on_reject: break, a non-AC subA
    # stops grading before subB is ever run, so the group's score is just subA's -- as high as
    # 100 -- even though grading both would pull the maximum average down to 55.
    subA = make_group('g.subA', [make_testcase('a')], range_='0 100', accept_score=100, reject_score=0)
    subB = make_group('g.subB', [make_testcase('b')], range_='0 10', accept_score=10, reject_score=0)
    group = make_group('g', [subA, subB], grader_flags='avg', on_reject='break', range_='0 100')
    assert _check_score_range(group, False, diag) == (0, 100)
    assert diag.messages == []


def test_avg_aggregator_with_on_reject_continue_is_tighter(diag):
    # Same as above, but without break: subB is always graded too, so avg is always over both.
    subA = make_group('g.subA', [make_testcase('a')], range_='0 100', accept_score=100, reject_score=0)
    subB = make_group('g.subB', [make_testcase('b')], range_='0 10', accept_score=10, reject_score=0)
    group = make_group('g', [subA, subB], grader_flags='avg', on_reject='continue', range_='0 55')
    assert _check_score_range(group, False, diag) == (0, 55)
    assert diag.messages == []


def test_reject_above_accept(diag):
    # Corner case: check we don't end up with a broken range if reject_score is above accept_score
    group = make_group('g', [make_testcase('a')], accept_score=0, reject_score=5)
    assert _check_score_range(group, False, diag) == (0, 5)


def test_custom_scoring_possible_is_unbounded(diag):
    group = make_group('g', [make_testcase('a')], accept_score=10, reject_score=0)
    assert _check_score_range(group, True, diag) == (-INF, INF)


def test_group_min_aggregator(diag):
    group = make_group(
        'g',
        [make_testcase('a'), make_testcase('b')],
        grader_flags='min',
    )
    # accept_score/reject_score are shared across a group's direct testcase children (1.0/0.0 here).
    assert _check_score_range(group, False, diag) == (0, 1)


def test_group_max_aggregator(diag):
    group = make_group('g', [make_testcase('a'), make_testcase('b')], grader_flags='max')
    assert _check_score_range(group, False, diag) == (0, 1)


def test_last_aggregator_flag_wins(diag):
    group = make_group('g', [make_testcase('a')], grader_flags='max min avg', accept_score=10, reject_score=0)
    assert _check_score_range(group, False, diag) == (0, 10)


def test_custom_grading_is_unbounded(diag):
    group = make_group('g', [make_testcase('a')], grading='custom')
    assert _check_score_range(group, False, diag) == (-INF, INF)


def test_empty_group_scores_zero(diag):
    group = make_group('g', [])
    assert _check_score_range(group, False, diag) == (0, 0)


def test_nested_groups_compose(diag):
    subtask1 = make_group(
        'g.subtask1',
        [make_testcase('a'), make_testcase('b')],
        grader_flags='min',
        range_='0 50',
        accept_score=50,
        reject_score=0,
    )
    subtask2 = make_group('g.subtask2', [make_testcase('c')], grader_flags='min', range_='0 50', accept_score=50, reject_score=0)
    secret = make_group('g.secret', [subtask1, subtask2], range_='0 100')
    assert _check_score_range(secret, False, diag) == (0, 100)
    assert diag.messages == []


def test_ignore_sample_at_root_skips_sample_group(diag):
    sample = make_group('sample', [make_testcase('s')], accept_score=1000, reject_score=0)
    secret = make_group('secret', [make_testcase('a')], accept_score=100, reject_score=0)
    root = make_group('data', [sample, secret], grader_flags='ignore_sample', is_root=True)
    assert _check_score_range(root, False, diag) == (0, 100)


def test_ignore_sample_is_a_no_op_below_root(diag):
    sample = make_group('sample', [make_testcase('s')], accept_score=1000, reject_score=0)
    secret = make_group('secret', [make_testcase('a')], accept_score=100, reject_score=0)
    # Misconfigured (checks._check_group flags this separately). We just aggregate all children
    non_root = make_group('g', [sample, secret], grader_flags='ignore_sample', is_root=False)
    assert _check_score_range(non_root, False, diag) == (0, 1100)


# --- Declared range vs. what can be inferred ---


def test_no_warning_when_declared_matches_computed(diag):
    group = make_group('g', [make_testcase('a')], range_='0 10', accept_score=10, reject_score=0)
    assert _check_score_range(group, False, diag) == (0, 10)
    assert diag.messages == []


def test_looser_declared_range_warns_and_suggests_tightening(diag):
    group = make_group('g', [make_testcase('a')], range_='0 100', accept_score=10, reject_score=0)
    assert _check_score_range(group, False, diag) == (0, 10)
    assert diag.messages == [
        (
            'warning',
            "Declared score range '0 100' for testcase group g is looser than the computed range [0, 10]; consider tightening it",
        )
    ]


def test_no_declared_range_warns_and_suggests_one(diag):
    group = make_group('g', [make_testcase('a')], accept_score=10, reject_score=0)  # range left at the default
    assert _check_score_range(group, False, diag) == (0, 10)
    assert diag.messages == [
        (
            'warning',
            (
                'No score range declared for testcase group g, but a range of [0, 10] can be computed from its '
                "grading configuration and test data; consider adding 'range: 0 10'"
            ),
        )
    ]


def test_narrower_declared_range_is_trusted_without_warning(diag):
    # A "bad guarantee": the group's own children can clearly reach 100, but the author declared a
    # narrower range. We don't warn -- that's a promise checked elsewhere (checks.submissions) --
    # but we do trust it for the returned (propagated) value.
    group = make_group('g', [make_testcase('a')], range_='0 10', accept_score=100, reject_score=0)
    assert _check_score_range(group, False, diag) == (0, 10)
    assert diag.messages == []


def test_narrower_declared_range_propagates_to_parent(diag):
    # The parent's aggregate must reflect the child's effective (trusted) range, not its raw
    # aggregate -- so a narrow declaration deep in the tree is reflected in ancestors' results too.
    bad_child = make_group('g.secret', [make_testcase('a')], range_='0 10', accept_score=100, reject_score=0)
    root = make_group('g', [bad_child], is_root=True)
    assert _check_score_range(root, False, diag) == (0, 10)
    # No warning at the child, but the root's default range is loose
    assert diag.messages == [
        (
            'warning',
            (
                'No score range declared for testcase group g, but a range of [0, 10] can be computed from its '
                "grading configuration and test data; consider adding 'range: 0 10'"
            ),
        )
    ]


def test_disjoint_declared_range_warns_distinctly(diag):
    group = make_group('g', [make_testcase('a')], range_='0 10', accept_score=100, reject_score=50)
    assert _check_score_range(group, False, diag) == (0, 10)
    assert diag.messages == [
        (
            'warning',
            "Declared score range '0 10' for testcase group g doesn't overlap with the computed range [50, 100] at all",
        )
    ]


def test_root_with_unbounded_aggregate_and_no_declared_range_still_warns(diag):
    group = make_group('g', [make_testcase('a')], grading='custom', is_root=True)
    assert _check_score_range(group, False, diag) == (-INF, INF)
    assert diag.messages == [
        (
            'warning',
            (
                'No score range declared for testcase group g, and none could be computed automatically; as the '
                'top-level group, its range is the overall score range for the problem -- consider declaring one '
                'explicitly'
            ),
        )
    ]


def test_non_root_with_unbounded_aggregate_and_no_declared_range_is_silent(diag):
    group = make_group('g', [make_testcase('a')], grading='custom', is_root=False)
    assert _check_score_range(group, False, diag) == (-INF, INF)
    assert diag.messages == []


def test_root_with_negative_minimum_and_no_other_issue_warns(diag):
    group = make_group('g', [make_testcase('a')], accept_score=10, reject_score=-5, range_='-5 10', is_root=True)
    assert _check_score_range(group, False, diag) == (-5, 10)
    assert diag.messages == [
        (
            'warning',
            (
                "Declared score range '-5 10' for testcase group g has a negative minimum; submissions with "
                'non-AC final verdict always have score 0, so a negative minimum is usually a mistake'
            ),
        )
    ]


def test_negative_minimum_below_root_is_not_flagged(diag):
    # negative scores for non-root test groups is a bit weird, but IMHO not weird enough to warn about
    group = make_group('g', [make_testcase('a')], accept_score=10, reject_score=-5, range_='-5 10', is_root=False)
    assert _check_score_range(group, False, diag) == (-5, 10)
    assert diag.messages == []


def test_negative_minimum_at_root_is_suppressed_by_other_warnings(diag):
    # Warning about a negative range is low priority. If we can instead suggest to narrow the range,
    # that's typically a better warning.
    group = make_group('g', [make_testcase('a')], accept_score=10, reject_score=0, range_='-10 200', is_root=True)
    assert _check_score_range(group, False, diag) == (0, 10)
    assert len(diag.messages) == 1
    assert 'looser than the computed range' in diag.messages[0][1]


def test_invalid_range_format_errors_and_falls_back_to_aggregate(diag):
    group = make_group('g', [make_testcase('a')], range_='not a range', accept_score=10, reject_score=0)
    assert _check_score_range(group, False, diag) == (0, 10)
    assert diag.errors == 1
    assert "Invalid format 'not a range'" in diag.messages[0][1]


def test_min_greater_than_max_errors_and_falls_back_to_aggregate(diag):
    group = make_group('g', [make_testcase('a')], range_='10 0', accept_score=10, reject_score=0)
    assert _check_score_range(group, False, diag) == (0, 10)
    assert diag.errors == 1
    assert 'cannot be greater than maximum score' in diag.messages[0][1]
