"""Apply a ``ThemeSpec`` to a site via WP-CLI.

Colors/fonts/footer are written as theme mods / options (the Customizer has no
reliable REST surface). Elementor global colors are best-effort: read the active
kit's settings, merge in the palette as system colors, write it back — so we
don't clobber other kit settings.
"""

from __future__ import annotations

import json
from typing import Any

from app.agent.skills.theme.schema import ThemeSpec
from app.wp.wpcli import WpCli


async def apply_theme(cli: WpCli, spec: ThemeSpec) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []

    async def step(name: str, coro) -> None:
        result = await coro
        results.append({"step": name, "ok": result.ok, "detail": result.stderr[:120]})

    # Colors + fonts as theme mods (generic keys; theme-specific keys vary).
    for key, value in spec.palette.model_dump().items():
        await step(f"color:{key}", cli.set_theme_mod(f"wpa_color_{key}", value))
    await step("font:heading", cli.set_theme_mod("wpa_font_heading", spec.fonts.heading))
    await step("font:body", cli.set_theme_mod("wpa_font_body", spec.fonts.body))
    if spec.footer_text:
        await step("footer_text", cli.set_option("wpa_footer_text", spec.footer_text))

    # Elementor global kit colors (best-effort, merge to avoid clobbering).
    kit = await cli.get_option("elementor_active_kit")
    kit_id = kit.stdout.strip()
    if kit.ok and kit_id.isdigit():
        current = await cli.get_post_meta(int(kit_id), "_elementor_page_settings")
        try:
            settings = json.loads(current.stdout) if current.stdout.strip() else {}
        except json.JSONDecodeError:
            settings = {}
        if not isinstance(settings, dict):
            settings = {}
        settings["system_colors"] = [
            {"_id": key, "title": key.title(), "color": value}
            for key, value in spec.palette.model_dump().items()
        ]
        await step(
            "elementor_kit_colors",
            cli.update_post_meta(
                int(kit_id), "_elementor_page_settings", json.dumps(settings),
                as_json=True,
            ),
        )
    else:
        results.append(
            {"step": "elementor_kit_colors", "ok": False, "detail": "no active kit"}
        )

    return results
