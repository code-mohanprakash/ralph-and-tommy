"""Ralph and Tommy as plain rules: no AI, no API key, the same every run.

The product is the Claude agent (agents/claude.py). These are its stand-ins for testing: they
run the harness, the rules, the vault and the bench for free, in seconds, with the same result
every time, so CI needs no key and the attackers have fixed rules to replay. They follow the same
limits the AI does: they learn about their limit only through bands.
"""

from fleek_agents.scripted.ralph import ScriptedRalph
from fleek_agents.scripted.tommy import BoulwareTommy, ScriptedTommy

__all__ = ["BoulwareTommy", "ScriptedRalph", "ScriptedTommy"]
