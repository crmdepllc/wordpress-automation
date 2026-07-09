"""Theme golden dataset: 3 briefs run through generate + apply (WP-CLI mocked)."""

from __future__ import annotations

from app.agent.skills.theme.applier import apply_theme
from app.agent.skills.theme.schema import ThemeFonts, ThemePalette, ThemeSpec
from app.agent.skills.theme.skill import generate_theme
from app.evals.scoring import CheckResult, Scenario
from app.wp.schemas import CliResult


class _FakeGenerator:
    def __init__(self, spec: ThemeSpec):
        self._spec = spec

    async def generate(self, brief: str) -> ThemeSpec:
        return self._spec


class _RecordingCli:
    """Captures WP-CLI calls the applier makes; simulates an active kit."""

    def __init__(self):
        self.theme_mods: dict[str, str] = {}
        self.options: dict[str, str] = {}
        self.kit_meta: str | None = None

    async def set_theme_mod(self, name, value):
        self.theme_mods[name] = value
        return CliResult(command=f"mod {name}", exit_code=0)

    async def set_option(self, name, value):
        self.options[name] = value
        return CliResult(command=f"opt {name}", exit_code=0)

    async def get_option(self, name):
        return CliResult(command="get", exit_code=0, stdout="7")

    async def get_post_meta(self, post_id, key):
        return CliResult(command="metaget", exit_code=0, stdout="{}")

    async def update_post_meta(self, post_id, key, value, *, as_json=False):
        self.kit_meta = value
        self.kit_meta_as_json = as_json
        return CliResult(command="metaset", exit_code=0)


_BRIEFS: dict[str, ThemeSpec] = {
    "dark minimal photography site": ThemeSpec(
        palette=ThemePalette(primary="#0d0d0d", secondary="#1a1a1a", accent="#c9a15a", text="#f5f5f5", background="#0d0d0d"),
        fonts=ThemeFonts(heading="Playfair Display", body="Inter"),
        footer_text="© Lens & Light",
    ),
    "playful colorful kids brand": ThemeSpec(
        palette=ThemePalette(primary="#ff5a5f", secondary="#ffd166", accent="#06d6a0", text="#222222", background="#fffdf7"),
        fonts=ThemeFonts(heading="Baloo 2", body="Nunito"),
        footer_text="© Sunny Kids Co.",
    ),
    "corporate SaaS trust-focused": ThemeSpec(
        palette=ThemePalette(primary="#0b3d91", secondary="#1e5fbf", accent="#00b894", text="#1a1a1a", background="#ffffff"),
        fonts=ThemeFonts(heading="Inter", body="Inter"),
        footer_text="© FlowPad, Inc.",
    ),
}


async def _run(brief: str, spec: ThemeSpec) -> list[CheckResult]:
    generated = await generate_theme(brief, generator=_FakeGenerator(spec))
    cli = _RecordingCli()
    results = await apply_theme(cli, generated)  # type: ignore[arg-type]

    all_ok = all(r["ok"] for r in results)
    palette_applied = all(f"wpa_color_{k}" in cli.theme_mods for k in spec.palette.model_dump())
    fonts_applied = "wpa_font_heading" in cli.theme_mods and "wpa_font_body" in cli.theme_mods
    footer_applied = not spec.footer_text or cli.options.get("wpa_footer_text") == spec.footer_text
    kit_merged = cli.kit_meta is not None
    # Must be a real PHP array via --format=json, not a plain JSON string —
    # a string fatals Elementor's Controls_Stack (found via live verification).
    kit_stored_as_array = getattr(cli, "kit_meta_as_json", False) is True
    return [
        CheckResult("all_wpcli_steps_ok", all_ok, weight=2),
        CheckResult("palette_applied", palette_applied, weight=1),
        CheckResult("fonts_applied", fonts_applied, weight=1),
        CheckResult("footer_applied", footer_applied, weight=1),
        CheckResult("elementor_kit_merged", kit_merged, weight=1),
        CheckResult("elementor_kit_stored_as_array", kit_stored_as_array, weight=2),
    ]


SCENARIOS = [
    Scenario(name=brief, run=lambda b=brief, s=spec: _run(b, s))
    for brief, spec in _BRIEFS.items()
]
