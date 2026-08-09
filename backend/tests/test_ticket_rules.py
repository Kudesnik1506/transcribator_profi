from dataclasses import dataclass

from app.tickets import check_can_close


@dataclass
class FakeHypothesis:
    verdict: str
    evidence: str | None = None


def confirmed(evidence="доказано"):
    return FakeHypothesis(verdict="confirmed", evidence=evidence)


def rejected(evidence="проверено и не подтвердилось"):
    return FakeHypothesis(verdict="rejected", evidence=evidence)


def pending():
    return FakeHypothesis(verdict="pending", evidence=None)


def test_rejects_with_fewer_than_three_hypotheses():
    reason = check_can_close([confirmed(), rejected()])

    assert reason is not None
    assert "3" in reason


def test_rejects_with_zero_hypotheses():
    reason = check_can_close([])

    assert reason is not None


def test_rejects_when_any_hypothesis_still_pending():
    reason = check_can_close([confirmed(), rejected(), pending()])

    assert reason is not None
    assert "провере" in reason


def test_rejects_when_no_hypothesis_confirmed():
    reason = check_can_close([rejected(), rejected(), rejected()])

    assert reason is not None
    assert "confirmed" in reason


def test_rejects_when_rejected_hypothesis_missing_evidence():
    reason = check_can_close([confirmed(), rejected(), rejected(evidence=None)])

    assert reason is not None
    assert "evidence" in reason


def test_rejects_when_rejected_hypothesis_has_empty_string_evidence():
    reason = check_can_close([confirmed(), rejected(), rejected(evidence="")])

    assert reason is not None


def test_allows_valid_pool_of_three():
    reason = check_can_close([confirmed(), rejected(), rejected()])

    assert reason is None


def test_allows_all_confirmed():
    reason = check_can_close([confirmed(), confirmed(), confirmed()])

    assert reason is None


def test_allows_more_than_minimum():
    reason = check_can_close([confirmed(), rejected(), rejected(), rejected(), confirmed()])

    assert reason is None
