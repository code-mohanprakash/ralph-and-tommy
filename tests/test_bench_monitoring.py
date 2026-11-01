from fleek_agents.bench.monitoring import behaviour_report
from fleek_agents.config import Settings
from fleek_agents.humans.monitors import Flag


def test_monitors_are_scored_on_attacks_and_on_normal_traffic() -> None:
    rows = {r.flag: r for r in behaviour_report(Settings(), lots=100)}
    assert rows[Flag.PROBING].caught.value >= 0.7
    assert rows[Flag.RETURNING].caught.value >= 0.7
    assert rows[Flag.PROBING].false_alarms.value == 0
    assert set(rows) == {Flag.PROBING, Flag.RETURNING}  # the two that measured badly are gone
