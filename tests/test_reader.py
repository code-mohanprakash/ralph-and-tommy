from fleek_agents.bench.scenarios import generate
from fleek_agents.bench.tactics import TACTICS, with_text
from fleek_agents.harness.reader import UNREAD, ListingFacts, ListingReader, marked, render
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
