from concurrent.futures import Future
from pathlib import Path
from typing import Any

import pytest

from problemtools.judge.cache import ResultStore
from problemtools.judge.result import SubmissionResult
from problemtools.model import Verdict, testdata
from problemtools.model.paths import AbsolutePath, RelativePath


def _testcase(
    tmp_path: Path,
    name: str,
    input_data: str = '1 2\n',
    answer_data: str = '3\n',
    output_validator_flags: list[str] | None = None,
) -> testdata.TestCase:
    infile = tmp_path / f'{name}.in'
    ansfile = tmp_path / f'{name}.ans'
    infile.write_text(input_data)
    ansfile.write_text(answer_data)
    return testdata.TestCase(
        infile=AbsolutePath(infile),
        ansfile=AbsolutePath(ansfile),
        path=RelativePath(Path(name)),
        input_validator_flags=[],
        output_validator_flags=output_validator_flags or [],
    )


def _result(verdict: Verdict, runtime: float, score: float | None = None) -> SubmissionResult:
    result = SubmissionResult(verdict, score=score)
    result.runtime = runtime
    return result


def _store(store: ResultStore, testcase: testdata.TestCase, result: SubmissionResult, run_timelim: float) -> None:
    assert store.claim(testcase)
    store.complete(testcase, result, run_timelim)


def _get(store: ResultStore, testcase: testdata.TestCase, timelim: float) -> SubmissionResult:
    result = store.get(testcase, timelim)
    assert isinstance(result, SubmissionResult)
    return result


def test_identical_testcases_shared(tmp_path: Path) -> None:
    a, b = _testcase(tmp_path, 'a'), _testcase(tmp_path, 'b')
    store = ResultStore()
    _store(store, a, SubmissionResult('AC', score=1.0), 1.0)
    assert not store.claim(b)
    result = _get(store, b, 1.0)
    assert result.score == 1.0
    assert result.test_node is b


@pytest.mark.parametrize(
    'difference',
    [{'input_data': '2 2\n'}, {'answer_data': '4\n'}, {'output_validator_flags': ['case_sensitive']}],
)
def test_different_testcases_not_shared(tmp_path: Path, difference: dict[str, Any]) -> None:
    a, b = _testcase(tmp_path, 'a'), _testcase(tmp_path, 'b', **difference)
    store = ResultStore()
    _store(store, a, _result('AC', 0.1), 1.0)
    assert store.get(b, 1.0) is None


def test_lower_timelim_gives_tle(tmp_path: Path) -> None:
    a = _testcase(tmp_path, 'a')
    store = ResultStore()
    _store(store, a, _result('AC', 0.8, score=1.0), 2.0)
    result = _get(store, a, 0.5)
    assert result.verdict == 'TLE'
    assert result.runtime == 0.8
    assert result.score is None
    assert _get(store, a, 1.0).verdict == 'AC'


def test_validator_first_wa_stays_wa_at_lower_timelim(tmp_path: Path) -> None:
    a = _testcase(tmp_path, 'a')
    store = ResultStore()
    wa = _result('WA', 0.8)
    wa.validator_first = True
    _store(store, a, wa, 2.0)
    result = _get(store, a, 0.5)
    assert result.verdict == 'WA'
    assert result.runtime == 0.5


def test_higher_timelim_than_run_timelim_not_served(tmp_path: Path) -> None:
    a = _testcase(tmp_path, 'a')
    store = ResultStore()
    _store(store, a, _result('AC', 0.1), 2.0)
    assert store.get(a, 3.0) is None


def test_in_flight_returns_future(tmp_path: Path) -> None:
    a, b = _testcase(tmp_path, 'a'), _testcase(tmp_path, 'b')
    store = ResultStore()
    assert store.claim(a)
    future_a, future_b = store.get(a, 2.0), store.get(b, 0.5)
    assert isinstance(future_a, Future) and isinstance(future_b, Future)
    assert not future_a.done() and not future_b.done()
    store.complete(a, _result('AC', 0.8), 2.0)
    result_a, result_b = future_a.result(timeout=1), future_b.result(timeout=1)
    assert (result_a.verdict, result_a.test_node) == ('AC', a)
    assert (result_b.verdict, result_b.test_node) == ('TLE', b)


def test_shared_result_not_mutated(tmp_path: Path) -> None:
    a, b = _testcase(tmp_path, 'a'), _testcase(tmp_path, 'b')
    store = ResultStore()
    result = _result('AC', 0.1)
    result.test_node = a
    result.runtime_testcase = a
    _store(store, a, result, 1.0)
    result_b = _get(store, b, 1.0)
    assert result_b.test_node is b and result_b.runtime_testcase is b
    assert result.test_node is a and result.runtime_testcase is a
    assert _get(store, a, 1.0).test_node is a
