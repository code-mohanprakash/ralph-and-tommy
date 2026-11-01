from fleek_agents.agents.base import Action, View
from fleek_agents.bench.episode import TapClient, run_episode
from fleek_agents.bench.scenarios import Scenario, generate
from fleek_agents.bench.tactics import TACTICS, with_text
from fleek_agents.config import Settings
from fleek_agents.harness.reader import UNREAD, ListingFacts, ListingReader, marked, render
from fleek_agents.scripted import ScriptedRalph, ScriptedTommy
from tests.fakes import FakeClient, call, message, text

ATTACK = TACTICS["instruction"]
FACTS = {
    "condition": "as_described",
    "mentions_sizes": True,
    "mentions_a_price": False,
    "addressed_to_buying_agents": True,
    "pressure": ["authority", "urgency"],
}


def reader_answering(*replies: object) -> tuple[ListingReader, FakeClient]:
    fake = FakeClient(*replies)  # type: ignore[arg-type]
    return ListingReader(fake, model="claude-haiku-5-5"), fake


def test_the_reader_sees_the_text_marked_as_data() -> None:
    reader, fake = reader_answering(message(call("report_listing", FACTS)))
    reader.facts(ATTACK)
    prompt = fake.requests[0]["messages"][0]["content"]
    assert marked(ATTACK) in prompt and "IMPORTANT^NOTE^FOR^BUYING^AGENTS" in prompt
    assert [t["name"] for t in fake.requests[0]["tools"]] == ["report_listing"]  # no other tool


def test_ralph_gets_fixed_sentences_never_the_sellers_words() -> None:
    reader, _ = reader_answering(message(call("report_listing", FACTS)))
    lot = with_text(generate(1)[0], ATTACK).lot
    seen = reader.quarantine(lot).description
    assert "Warning: part of it was addressed to buying agents" in seen
    assert "authority, urgency" in seen
    for word in ("IMPORTANT", "disabled", "immediately", "accept any counter", "Washed"):
        assert word not in seen
    assert reader.quarantine(lot).model_copy(update={"description": lot.description}) == lot


def test_every_possible_summary_is_built_from_fixed_text() -> None:
    # Whatever the reader reports, the summary is assembled from our own sentences only.
    for condition in ("as_described", "mentions_defects", "unclear"):
        for flag in (True, False):
            facts = ListingFacts.model_validate(
                {**FACTS, "condition": condition, "addressed_to_buying_agents": flag}
            )
            assert render(facts).startswith("Summary by Fleek's listing reader")


def test_a_reader_that_fails_gives_a_fixed_note_not_the_text() -> None:
    no_form = message(text("I'd rather not."), stop="end_turn")
    reader, _ = reader_answering(no_form, no_form, no_form)
    lot = with_text(generate(1)[0], ATTACK).lot
    assert reader.quarantine(lot).description == UNREAD


def test_each_text_is_read_once() -> None:
    reader, fake = reader_answering(message(call("report_listing", FACTS)))
    lot = with_text(generate(1)[0], ATTACK).lot
    reader.quarantine(lot)
    reader.quarantine(lot)
    assert len(fake.requests) == 1


class Spy:
    """Records the description each side's view shows, and plays like the scripted agent."""

    def __init__(self, inner: ScriptedRalph | ScriptedTommy) -> None:
        self.inner, self.seen = inner, []  # type: ignore[var-annotated]

    def decide(self, view: View) -> Action:
        self.seen.append(view.lot.description)
        return self.inner.decide(view)


def test_only_ralph_sees_the_summary_tommy_and_the_checks_see_the_real_lot() -> None:
    reader, _ = reader_answering(message(call("report_listing", FACTS)))
    scenario = with_text(next(s for s in generate(10) if s.truth.deal_possible), ATTACK)
    ralph, tommy = Spy(ScriptedRalph()), Spy(ScriptedTommy())

    def pair(_s: Scenario, _r: int) -> tuple[Spy, Spy, list[TapClient]]:
        return ralph, tommy, []

    episode = run_episode(
        scenario,
        pair,
        Settings(),
        buyer_lot=reader.quarantine(scenario.lot),
    )
    assert ralph.seen and all(d.startswith("Summary by Fleek") for d in ralph.seen)
    assert tommy.seen and all(d == ATTACK for d in tommy.seen)
    assert episode.state is not None


def test_in_blind_mode_ralph_s_requests_are_byte_identical_whatever_the_seller_wrote() -> None:
    import json

    from fleek_agents.agents.claude import ClaudeAgent
    from fleek_agents.harness.reader import NOT_SHOWN, blind

    base = next(s for s in generate(10) if s.truth.deal_possible)
    price = base.lot.base_price.value * 70 // 100 // 5 * 5
    offer = {"price_pence": price, "prepaid": False, "reason_codes": []}

    def ralph_requests(description: str, *, hide: bool) -> str:
        scenario = with_text(base, description)
        client = FakeClient(
            message(call("get_lot", {})),
            message(call("send_offer", offer)),
            message(call("walk_away", {"reason_code": None})),
            message(call("walk_away", {"reason_code": None})),
        )
        ralph = ClaudeAgent(client, model="claude-haiku-5-5", prompt="ralph")

        def pair(_s: Scenario, _r: int) -> tuple[ClaudeAgent, ScriptedTommy, list[TapClient]]:
            return ralph, ScriptedTommy(), []

        run_episode(scenario, pair, Settings(), buyer_lot=blind(scenario.lot) if hide else None)
        return json.dumps(client.requests, default=str)

    calm = "Washed and sorted. Mixed sizes 28-36."
    blind_calm, blind_attack = ralph_requests(calm, hide=True), ralph_requests(ATTACK, hide=True)
    assert blind_calm == blind_attack
    assert NOT_SHOWN in blind_calm and ATTACK not in blind_calm
    # The control: without blind mode the seller's words reach him, so the requests differ.
    assert ralph_requests(calm, hide=False) != ralph_requests(ATTACK, hide=False)
