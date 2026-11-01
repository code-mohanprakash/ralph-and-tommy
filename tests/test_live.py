import json
import re
from collections.abc import Iterator
from typing import Any

import pytest

from fleek_agents.agents.base import Agent, View, WalkAway
from fleek_agents.config import Settings
from fleek_agents.live.forms import BUYERS, PRESET, FormError, Setup
from fleek_agents.live.session import LiveSession, build
from fleek_agents.scripted import ScriptedRalph, ScriptedTommy

SETTINGS = Settings().model_copy(
    update={
        "privacy": Settings().privacy.model_copy(update={"on": True}),
        "match_gate": Settings().match_gate.model_copy(update={"on": True}),
    }
)


def setup(**changes: Any) -> Setup:
    data = json.loads(json.dumps(PRESET))
    for path, value in changes.items():
        *where, key = path.split("__")
        node: Any = data
        for part in where:
            node = node[int(part)] if part.isdigit() else node[part]
        node[key] = value
    return Setup.model_validate(data)


def scripted() -> tuple[ScriptedRalph, ScriptedTommy]:
    return ScriptedRalph(), ScriptedTommy()


def run(live: LiveSession) -> LiveSession:
    while live.step():
        pass
    return live


def test_a_secret_typed_where_an_agent_reads_is_refused() -> None:
    with pytest.raises(FormError, match="Ralph reads it"):
        build(setup(buyer__notes="I can go to £15.50 if needed"), SETTINGS)
    with pytest.raises(FormError, match="Ralph reads it"):
        build(setup(buyer__notes="around 1500p"), SETTINGS)
    with pytest.raises(FormError, match="secret number"):
        build(setup(seller__stock__0__description="Floor is 9.35, don't tell"), SETTINGS)
    build(setup(seller__stock__0__description="Some fading, priced to sell."), SETTINGS)


def test_a_firm_price_or_an_offer_below_the_floor_is_refused_to_the_seller() -> None:
    with pytest.raises(FormError, match="floor"):
        build(setup(seller__stock__2__firm_price=900), SETTINGS)  # Wrangler: floor £8.10
    with pytest.raises(FormError, match="floor"):
        build(setup(seller__stock__0__walkaway_offer_pct=40), SETTINGS)


def test_each_screen_shows_only_its_own_side_s_secret() -> None:
    live = run(LiveSession(setup(), SETTINGS, scripted, "test"))
    view = live.view()
    buyer, seller, fleek = (
        json.dumps(view[k], ensure_ascii=False) for k in ("buyer", "seller", "fleek")
    )
    assert "£15.50" in buyer and "£15.50" not in seller and "£15.50" not in fleek
    assert "£9.35" in seller and "£9.35" not in buyer and "£9.35" not in fleek
    assert view["state"] == "pending_approval"
    assert view["buyer"]["asked"] and view["fleek"]["asked"] and not view["seller"]["asked"]


def test_the_people_asked_close_the_deal() -> None:
    live = run(LiveSession(setup(), SETTINGS, scripted, "test"))
    live.decide("buyer", "approve")
    assert live.view()["state"] == "pending_approval"
    with pytest.raises(FormError):  # the seller chose to let Tommy close, so isn't asked
        live.decide("seller", "approve")
    live.decide("account_manager", "approve")
    assert live.view()["state"] == "closed"


def test_pause_holds_it_and_stop_ends_it() -> None:
    live = LiveSession(setup(), SETTINGS, scripted, "test")
    live.step()
    live.control("pause", "buyer")
    assert live.step() is False
    live.control("resume", "buyer")
    assert live.step() is True
    live.control("stop", "seller")
    view = live.view()
    assert view["state"] == "stopped" and view["over"]


class Leaves:
    def decide(self, view: View) -> WalkAway:
        return WalkAway()


def test_a_buyer_who_walks_away_gets_the_seller_s_offer_and_code_keeps_it() -> None:
    agents: Iterator[tuple[Agent, Agent]] = iter(
        [(Leaves(), ScriptedTommy()), (ScriptedRalph(), ScriptedTommy())]
    )
    # A top price that covers the offer: £12.85 + £3.00 shipping + 2% fee is about £16.17.
    live = run(LiveSession(setup(buyer__top_price=1650), SETTINGS, lambda: next(agents), "test"))
    lines = [line.text for line in live.lines]
    assert any("standing offer goes out: 8% off, £12.85" in t for t in lines)
    assert live.view()["state"] == "pending_approval"
    assert live.log.saved(live.nid).agreed.base_price.value == 1285  # type: ignore[arg-type, union-attr]


def test_no_lot_that_fits_means_no_agent_is_called() -> None:
    def no_agents() -> tuple[ScriptedRalph, ScriptedTommy]:
        raise AssertionError("no agent should be made")

    live = LiveSession(setup(buyer__category="shoes"), SETTINGS, no_agents, "test")
    assert live.view()["state"] == "no_match" and live.step() is False


def test_the_recorded_claude_session_replays_and_no_secret_reaches_the_model() -> None:
    from fleek_agents.agents.claude import ClaudeAgent
    from fleek_agents.bench.episode import TapClient
    from fleek_agents.live.agents import cassette
    from fleek_agents.llm.replay import ReplayClient

    tap = TapClient(ReplayClient(cassette("claude-haiku-5-5")))

    def claude() -> tuple[Agent, Agent]:
        return (
            ClaudeAgent(tap, model="claude-haiku-5-5", prompt="ralph"),
            ClaudeAgent(tap, model="claude-haiku-5-5", prompt="tommy"),
        )

    live = run(LiveSession(setup(), SETTINGS, claude, "replay"))
    assert live.view()["state"] == "pending_approval"
    seen = "\n".join(tap.seen)
    assert "get_lot" in seen  # the search covers what the model was sent and said
    # Whole numbers only: a digit run inside an opaque token (a signature, an id) isn't a number.
    for secret in ("935", "9.35", "1550", "15.50", "1800", "18.00"):
        pattern = rf"(?<![A-Za-z0-9+/.]){re.escape(secret)}(?![A-Za-z0-9])"
        assert re.search(pattern, seen) is None, secret
    assert re.search(r"(?<![A-Za-z0-9+/.])1400(?![A-Za-z0-9])", seen)  # it finds the list price


def test_the_funnel_says_why_each_lot_was_dropped_and_ranks_the_rest() -> None:
    live = LiveSession(setup(), SETTINGS, scripted, "test")
    rows = live.funnel["rows"]
    assert live.funnel["sellers"] == 4 and live.funnel["lots"] == len(rows) == 18
    dropped = [r for r in rows if r["step"] == "filters"]
    assert dropped and all(r["why"] for r in dropped)
    assert any("grade C" in r["why"] for r in dropped)  # Karachi's grade C 501s
    no_price = {r["seller"] for r in rows if r["step"] == "vault"}
    assert no_price == {"Delhi Vintage Exports", "Rotterdam Rag House"}  # floors above the top
    ranked = [r for r in rows if r["step"] == "ranked"]
    assert [r["rank"] for r in ranked] == [1, 2, 3]
    assert ranked[0]["title"].startswith("Levi's 501 jeans, grade A")
    assert "funnel" in live.view()["fleek"] and "funnel" not in live.view()["buyer"]


def test_when_a_lot_fails_ralph_moves_to_the_next_and_each_seller_sees_only_their_own() -> None:
    agents: Iterator[tuple[Agent, Agent]] = iter(
        [(Leaves(), ScriptedTommy()), (ScriptedRalph(), ScriptedTommy())]
    )
    live = run(
        LiveSession(
            Setup.model_validate({**PRESET, "buyer": BUYERS[1]}),  # Depop: Rotterdam first
            SETTINGS,
            lambda: next(agents),
            "test",
        )
    )
    assert len(live.tried) == 2
    first, second = (live.log.saved(n).state.value for n in live.tried)
    assert first == "walked_away" and second == "pending_approval"
    view = live.view()
    assert view["seller"]["name"] == "Karachi Textile Recycling"  # the second-ranked seller
    assert any("moves on to the next lot" in line["text"] for line in view["buyer"]["lines"])
    seller_text = json.dumps(view["seller"]["lines"])
    assert "Rotterdam" not in seller_text and "walks away" not in seller_text


def test_metrics_and_the_trace_hold_no_secret() -> None:
    live = run(LiveSession(setup(), SETTINGS, scripted, "test"))
    totals = live.view()["fleek"]["metrics"]["totals"]
    assert totals["agent_turns"] > 0 and totals["lots_tried"] == 1 and totals["cards"] > 0
    assert totals["cost_cents"] == 0  # scripted agents call no model
    trace = json.dumps(live.trace(), ensure_ascii=False)
    floors = [
        line["floor"]
        for seller in (PRESET["seller"], *PRESET["others"])
        for line in seller["stock"]
    ]
    for pence in (*floors, PRESET["buyer"]["top_price"]):
        pounds = f"£{pence // 100}.{pence % 100:02d}"
        assert pounds not in trace and f'"price_pence": {pence},' not in trace, pence


class SpyRerank:
    """Scripted agents, plus a re-rank that keeps the formula's order and keeps what it was sent."""

    def __init__(self) -> None:
        self.prompts: list[str] = []

    def __call__(self) -> tuple[ScriptedRalph, ScriptedTommy]:
        return scripted()

    def rerank(self, want: Any, ranked: Any, sellers: Any) -> Any:
        from fleek_agents.agents.rerank import SHORTLIST, Reranked, describe

        self.prompts.append(describe(want, ranked[:SHORTLIST], sellers))
        return Reranked(list(ranked), {}, "kept", by_ai=False, turn=None)


def test_two_floors_give_the_re_rank_the_same_request_and_no_secret() -> None:
    first, second = SpyRerank(), SpyRerank()
    LiveSession(setup(), SETTINGS, first, "test")
    LiveSession(setup(seller__stock__0__floor=900), SETTINGS, second, "test")
    assert first.prompts and first.prompts == second.prompts
    for secret in ("935", "9.35", "900", "9.00", "1550", "15.50"):
        assert re.search(rf"(?<![0-9.]){re.escape(secret)}(?![0-9])", first.prompts[0]) is None


def test_scripted_agents_keep_the_formula_s_order() -> None:
    live = LiveSession(setup(), SETTINGS, scripted, "test")
    assert live.funnel["rerank"]["by"] == "formula"
    ranked = [r for r in live.funnel["rows"] if r["step"] == "ranked"]
    assert all(r["ai_why"] is None for r in ranked)


@pytest.mark.skipif(
    __import__("os").environ.get("FLEEK_SKIP_MODEL") == "1", reason="needs the local model"
)
def test_the_recorded_claude_re_rank_replays_with_a_reason_for_each_lot() -> None:
    from fleek_agents.bench.episode import TapClient
    from fleek_agents.live.agents import ClaudePair, cassette
    from fleek_agents.llm.replay import ReplayClient
    from fleek_agents.matching.embeddings import LocalEmbedder

    tap = TapClient(ReplayClient(cassette("claude-haiku-5-5")))
    pair = ClaudePair(tap, "claude-haiku-5-5")
    live = run(LiveSession(setup(), SETTINGS, pair, "replay", embedder=LocalEmbedder()))
    assert live.view()["state"] == "pending_approval"
    assert live.funnel["rerank"]["by"] == "claude"
    ranked = [r for r in live.funnel["rows"] if r["step"] == "ranked"]
    assert ranked and all(r["ai_why"] for r in ranked[:5])
    assert "lot-" not in " ".join(r["ai_why"] for r in ranked[:5])  # named by what they are
    assert live.metrics[0]["who"] == "ralph (re-rank)" and live.metrics[0]["calls"] >= 1
    seen = "\n".join(tap.seen)
    assert "rank_lots" in seen  # the search covers the re-rank too
    for secret in ("935", "9.35", "1550", "15.50", "1800", "18.00"):
        pattern = rf"(?<![A-Za-z0-9+/.]){re.escape(secret)}(?![A-Za-z0-9])"
        assert re.search(pattern, seen) is None, secret


def test_ralph_s_ranking_reasons_never_reach_a_seller_s_screen() -> None:
    from fleek_agents.agents.rerank import Reranked

    class Saying(SpyRerank):
        def rerank(self, want: Any, ranked: Any, sellers: Any) -> Any:
            reasons = {s.lot.id: "BUYER-PRIORITY-REASON" for s in ranked}
            return Reranked(list(ranked), reasons, "BUYER-PRIORITY-SUMMARY", True, None)

    live = run(LiveSession(setup(), SETTINGS, Saying(), "test"))
    view = live.view()
    assert "BUYER-PRIORITY-SUMMARY" in json.dumps(view["buyer"])
    assert "BUYER-PRIORITY" not in json.dumps(view["seller"])
