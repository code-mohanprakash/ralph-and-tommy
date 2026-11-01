"""The trade-off: how much hiding the floor costs in deals. One point per setting, one chart.

For each setting (Tommy's style, the secret margin, the noise), two numbers:
- leak: how often the strongest attacker gets within 2% of the floor;
- deals: how often a deal closes where one could.
Hiding a floor that Tommy acts on always costs some deals, so the chart is how we choose.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from fleek_agents.agents.base import Agent
from fleek_agents.agents.scripted import BoulwareTommy, ScriptedRalph, ScriptedTommy
from fleek_agents.bench.episode import TapClient
from fleek_agents.bench.moves import LeakScore, moves_report
from fleek_agents.bench.run import run_suite
from fleek_agents.bench.scenarios import Scenario, generate
from fleek_agents.bench.score import summarise
from fleek_agents.bench.stats import Estimate
from fleek_agents.config import PrivacyRules, Settings

STYLES: dict[str, Callable[[], ScriptedTommy]] = {
    "thirds": ScriptedTommy,
    "boulware": BoulwareTommy,
}
# (style, margin %, noise %): the plain ones, each lever alone, and the combinations.
GRID = (
    ("thirds", 0, 0),
    ("thirds", 0, 4),
    ("thirds", 4, 0),
    ("thirds", 8, 0),
    ("thirds", 8, 4),
    ("boulware", 0, 0),
    ("boulware", 4, 0),
    ("boulware", 5, 0),
    ("boulware", 6, 0),
)
# Pass marks, written down before measuring (tasks/deep-dive-plan.md, section 4).
LEAK_CUT = 0.40  # the strongest attacker's hit rate falls by at least this share...
MAX_DEALS_LOST = 0.05  # ...while losing fewer than this many points of deals


@dataclass(frozen=True)
class Point:
    style: str
    margin: int
    noise: int
    strongest: LeakScore  # the attacker with the highest hit rate at this setting
    deals: Estimate
    buyer_share: Estimate

    @property
    def label(self) -> str:
        return f"{self.style}, margin {self.margin}%, noise {self.noise}%"

    def passes(self, before: "Point") -> bool:
        cut = 1 - self.strongest.within.value / before.strongest.within.value
        lost = before.deals.value - self.deals.value
        return cut >= LEAK_CUT and lost < MAX_DEALS_LOST


def settings_for(base: Settings, margin: int, noise: int) -> Settings:
    rules = PrivacyRules(on=margin + noise > 0, margin_max_pct=margin, noise_pct=noise)
    return base.model_copy(update={"privacy": rules})


def measure(
    base: Settings,
    style: str,
    margin: int,
    noise: int,
    *,
    lots: int,
    deal_scenarios: Sequence[Scenario],
) -> Point:
    model = STYLES[style]
    settings = settings_for(base, margin, noise)

    def tommy(_scenario: Scenario) -> tuple[Agent, list[TapClient]]:
        return model(), []

    def pair(_scenario: Scenario, _run: int) -> tuple[Agent, Agent, list[TapClient]]:
        return ScriptedRalph(), model(), []

    rows = moves_report(settings, tommy=tommy, model=model, lots=lots)
    summary = summarise(run_suite(deal_scenarios, pair, settings))
    return Point(
        style,
        margin,
        noise,
        max(rows, key=lambda r: r.within.value),
        summary.deal_rate,
        summary.buyer_share,
    )


def sweep(
    base: Settings,
    grid: Sequence[tuple[str, int, int]] = GRID,
    *,
    lots: int = 100,
    deal_lots: int = 200,
    progress: Callable[[str], None] = lambda _: None,
) -> list[Point]:
    deal_scenarios = generate(deal_lots)
    points = []
    for style, margin, noise in grid:
        progress(f"{style}, margin {margin}%, noise {noise}%")
        points.append(measure(base, style, margin, noise, lots=lots, deal_scenarios=deal_scenarios))
    return points


def chart(points: Sequence[Point]) -> str:
    """An SVG scatter: deals closed (across) against the strongest attacker's hit rate (up).

    Dots are numbered, with a key on the right, so no label can drift away from its dot.
    Settings that pass both marks get a ring.
    """
    width, height, pad, plot_right = 980, 460, 70, 650
    xs = [p.deals.value for p in points]
    x_low, x_high = min(xs) - 0.02, max(xs) + 0.01
    y_high = max(p.strongest.within.value for p in points) + 0.08

    def x(v: float) -> float:
        return pad + (v - x_low) / (x_high - x_low) * (plot_right - pad)

    def y(v: float) -> float:
        return height - pad - v / y_high * (height - 2 * pad)

    before = points[0]
    target_y = y(before.strongest.within.value * (1 - LEAK_CUT))
    target_x = x(before.deals.value - MAX_DEALS_LOST)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        'font-family="Helvetica, Arial, sans-serif" font-size="12">',
        f'<rect width="{width}" height="{height}" fill="white"/>',
        f'<rect x="{target_x:.0f}" y="{target_y:.0f}" width="{plot_right - target_x:.0f}" '
        f'height="{height - pad - target_y:.0f}" fill="#e6f4ea"/>',
        f'<text x="{plot_right - 6}" y="{height - pad - 8}" text-anchor="end" fill="#1e7b34">'
        "passes both marks</text>",
        f'<line x1="{pad}" y1="{height - pad}" x2="{plot_right}" y2="{height - pad}" '
        'stroke="#333"/>',
        f'<line x1="{pad}" y1="{pad}" x2="{pad}" y2="{height - pad}" stroke="#333"/>',
        f'<text x="{(pad + plot_right) / 2}" y="{height - 25}" text-anchor="middle">'
        "Deals closed, where a deal works (higher is better)</text>",
        f'<text x="18" y="{height / 2}" text-anchor="middle" '
        f'transform="rotate(-90 18 {height / 2})">'
        "Strongest attacker within 2% of the floor (lower is better)</text>",
        f'<text x="{width / 2}" y="30" text-anchor="middle" font-size="15" font-weight="bold">'
        "Hiding Tommy's floor costs deals: every setting measured</text>",
        f'<text x="{plot_right + 30}" y="{pad}" font-weight="bold">Setting: attacker hit rate, '
        "deals closed</text>",
    ]
    for tick in range(0, int(y_high * 100) + 1, 10):
        parts.append(
            f'<text x="{pad - 8}" y="{y(tick / 100) + 4:.0f}" text-anchor="end">{tick}%</text>'
        )
    for i in range(5):
        v = x_low + (x_high - x_low) * i / 4
        parts.append(
            f'<text x="{x(v):.0f}" y="{height - pad + 18}" text-anchor="middle">{v:.0%}</text>'
        )
    for number, p in enumerate(points, start=1):
        colour = "#1a73e8" if p.style == "thirds" else "#e8710a"
        cx, cy = x(p.deals.value), y(p.strongest.within.value)
        if p is not before and p.passes(before):
            parts.append(
                f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="11" fill="none" stroke="#1e7b34" '
                'stroke-width="2"/>'
            )
        parts.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="7" fill="{colour}"/>')
        parts.append(
            f'<text x="{cx:.1f}" y="{cy + 4:.1f}" text-anchor="middle" fill="white" '
            f'font-size="10" font-weight="bold">{number}</text>'
        )
        key_y = pad + 24 + (number - 1) * 22
        parts.append(f'<circle cx="{plot_right + 38}" cy="{key_y - 4}" r="7" fill="{colour}"/>')
        parts.append(
            f'<text x="{plot_right + 38}" y="{key_y}" text-anchor="middle" fill="white" '
            f'font-size="10" font-weight="bold">{number}</text>'
        )
        parts.append(
            f'<text x="{plot_right + 52}" y="{key_y}">{p.style}, margin {p.margin}%, '
            f"noise {p.noise}%: {p.strongest.within.value:.0%}, {p.deals.value:.0%}</text>"
        )
    parts.append("</svg>")
    return "\n".join(parts)
