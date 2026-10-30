from pathlib import Path

from sqlalchemy.orm import Session

from fleek_agents.agents.base import HandOff, Send
from fleek_agents.agents.claude import ClaudeAgent, turn_prompt
from fleek_agents.agents.scripted import ScriptedTommy
from fleek_agents.config import Settings
from fleek_agents.domain.events import EscalationReason
from fleek_agents.domain.money import Pence
from fleek_agents.domain.state import NegotiationState
from fleek_agents.llm.env import load_env_file
from fleek_agents.llm.replay import cassette_client
from fleek_agents.orchestrator.clock import FakeClock
from fleek_agents.orchestrator.opening import open_negotiation
from fleek_agents.orchestrator.run import run_negotiation
from fleek_agents.store.db import Base, make_engine
from fleek_agents.store.deals import put_on_sale
from fleek_agents.store.events import EventLog
from fleek_agents.vault.checks import can_accept
from tests.fakes import FakeClient, call, message, text
from tests.test_agent_tools import view
from tests.test_scripted import LOT, SELLER, T0, WANT, limits

CASSETTES = Path(__file__).parent / "cassettes"


def test_an_offer_from_the_model_becomes_a_send() -> None:
    offer = {"price_pence": 1100, "prepaid": False, "reason_codes": ["bulk"]}
    client = FakeClient(
        message(call("check_price", {"price_pence": 1100})), message(call("send_offer", offer))
    )
    action = ClaudeAgent(client, model="claude-haiku-5-5", prompt="ralph").decide(view(True))
    assert isinstance(action, Send) and action.terms.base_price == Pence(1100)


def test_a_refusal_becomes_a_hand_off() -> None:
    agent = ClaudeAgent(
        FakeClient(message(text(""), stop="refusal")), model="claude-haiku-5-5", prompt="ralph"
    )
    assert agent.decide(view(True)) == HandOff(reason=EscalationReason.MODEL_REFUSED)


def test_what_the_model_is_told_holds_no_secret() -> None:
    client = FakeClient(message(call("walk_away", {"reason_code": None})))
    ClaudeAgent(client, model="claude-haiku-5-5", prompt="ralph").decide(view(True))
    sent = str(client.requests[0])  # system prompt, turn prompt, tool definitions
    for secret in ("1873", "18.73", "1137", "11.37"):
        assert secret not in sent
    assert "list" in turn_prompt(view(True)) or "turn" in turn_prompt(view(True))


def test_claude_ralph_closes_a_deal_with_scripted_tommy_inside_both_limits() -> None:
    # Recorded once live (FLEEK_LIVE=1 FLEEK_RECORD=1); replayed offline everywhere else.
    load_env_file(Path(__file__).parents[1] / ".env")
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = Session(engine)
    log, clock, settings = EventLog(session), FakeClock(T0), Settings()
    put_on_sale(session, LOT.id, bundles=1)
    nid = open_negotiation(
        log, buyer_id="buyer-0001", lot_id=LOT.id, clock=clock, rules=settings.negotiation
    )
    buyer_limit, seller_limit = limits(max_pence=1600, floor_pence=950)
    ralph = ClaudeAgent(
        cassette_client(CASSETTES / "ralph_vs_scripted_tommy.jsonl"),
        model="claude-haiku-5-5",
        prompt="ralph",
    )
    state = run_negotiation(
        log,
        nid,
        lot=LOT,
        seller=SELLER,
        want=WANT,
        bundles=1,
        buyer_limit=buyer_limit,
        seller_limit=seller_limit,
        ralph=ralph,
        tommy=ScriptedTommy(),
        clock=clock,
        settings=settings,
    )
    cards = [e.card for e in log.read(nid) if e.card is not None]
    print("\n" + " | ".join(f"{c.from_role} {c.base_price}" for c in cards), "->", state)
    used = (sum(t.calls for t in ralph.turns), sum(t.input_tokens for t in ralph.turns))
    print(f"{used[0]} calls, {used[1]} input tokens")
    assert state is NegotiationState.PENDING_APPROVAL
    agreed = log.saved(nid).agreed
    assert agreed is not None
    assert can_accept(
        buyer_limit, seller_limit, base_price=agreed.base_price, shipping=LOT.shipping, pieces=50
    )
