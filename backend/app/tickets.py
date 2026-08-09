MIN_HYPOTHESES = 3


class HypothesisLike:
    """Structural type — anything with .verdict and .evidence works (ORM row or plain object)."""

    verdict: str
    evidence: str | None


def check_can_close(hypotheses: list) -> str | None:
    """Returns a Russian reason the ticket can't move to fix_ready yet, or
    None if the gate is satisfied. Pure and DB-free on purpose — the rule
    that "no single hypothesis is ever trusted" has to be enforceable
    without a running server to verify it holds.
    """
    if len(hypotheses) < MIN_HYPOTHESES:
        return f"нужно записать не меньше {MIN_HYPOTHESES} гипотез — сейчас {len(hypotheses)}"

    pending = [h for h in hypotheses if h.verdict == "pending"]
    if pending:
        return f"не проверено гипотез: {len(pending)} — у каждой должен быть вердикт confirmed или rejected"

    confirmed = [h for h in hypotheses if h.verdict == "confirmed"]
    if not confirmed:
        return "ни одна гипотеза не подтверждена — должна быть хотя бы одна confirmed"

    unproven_rejections = [h for h in hypotheses if h.verdict == "rejected" and not h.evidence]
    if unproven_rejections:
        return "у отвергнутых гипотез должно быть заполнено evidence — чем проверялась и что показало"

    return None
