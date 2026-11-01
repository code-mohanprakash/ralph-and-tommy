"""The test bench: many generated deals, attacks on them, and scores with error bars.

Modelled on how 2026 negotiation benchmarks and AI labs test agents (docs/SAFETY_CASE.md lists
the sources): the evaluator knows both secret limits, the agents never do, and every score
comes with a 95% interval instead of one run's result.
"""
