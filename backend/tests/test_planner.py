"""Unit tests for the LLM planner (model mocked)."""

from __future__ import annotations

from app.agent.orchestrator.planner import LLMPlanner


class FakeResponse:
    def __init__(self, tool_calls):
        self.tool_calls = tool_calls


class FakeLLM:
    def __init__(self, tool_calls):
        self._tool_calls = tool_calls

    def bind_tools(self, tools):
        return self

    async def ainvoke(self, messages):
        return FakeResponse(self._tool_calls)


async def test_plan_builds_ordered_steps_with_previews():
    llm = FakeLLM(
        [
            {"name": "wp_install_plugin", "args": {"plugin_slug": "elementor"}},
            {"name": "wp_create_page", "args": {"title": "Home"}},
        ]
    )
    steps = await LLMPlanner(llm=llm).plan("install then create home", "acme")

    assert [s.tool for s in steps] == ["wp_install_plugin", "wp_create_page"]
    assert [s.id for s in steps] == ["step-0", "step-1"]
    # site_slug is injected into every step regardless of model output.
    assert all(s.args["site_slug"] == "acme" for s in steps)
    # Both are writes → gated, with a needs_approval preview (no site touched).
    assert all(s.requires_approval for s in steps)
    assert steps[0].preview["status"] == "needs_approval"
    assert steps[0].channel == "WP-CLI"
    assert steps[1].channel == "REST API"


async def test_plan_empty_when_no_tool_calls():
    steps = await LLMPlanner(llm=FakeLLM([])).plan("hello", "acme")
    assert steps == []


async def test_plan_reorders_by_category_precedence():
    # Emitted out of order (content, theme, page); precedence is
    # plugin < theme < page < content < seo < menu.
    llm = FakeLLM(
        [
            {"name": "wp_publish_post", "args": {"brief": "hello"}},
            {"name": "wp_apply_theme", "args": {"brief": "dark minimal"}},
            {"name": "wp_create_page", "args": {"title": "Home"}},
        ]
    )
    steps = await LLMPlanner(llm=llm).plan("build a themed site with a post", "acme")

    assert [s.tool for s in steps] == [
        "wp_apply_theme",
        "wp_create_page",
        "wp_publish_post",
    ]
    assert [s.category for s in steps] == ["theme", "page", "content"]
    # ids are stable (assigned at emission time), only the order changes.
    assert [s.id for s in steps] == ["step-1", "step-2", "step-0"]


async def test_plan_ref_creates_explicit_dependency():
    # SEO step references a page step's id via $ref; category precedence
    # already orders page before seo, and the ref confirms the dependency.
    llm = FakeLLM(
        [
            {
                "name": "wp_apply_seo",
                "args": {
                    "target_id": "$ref:step-1:page.id",
                    "target_type": "page",
                    "subject": "About us",
                },
            },
            {"name": "wp_create_page", "args": {"title": "About"}},
        ]
    )
    steps = await LLMPlanner(llm=llm).plan("create an About page with SEO", "acme")

    assert [s.id for s in steps] == ["step-1", "step-0"]
    seo_step = next(s for s in steps if s.tool == "wp_apply_seo")
    assert seo_step.depends_on == ["step-1"]


async def test_plan_menu_depends_on_pages_and_posts():
    llm = FakeLLM(
        [
            {"name": "wp_create_page", "args": {"title": "Home"}},
            {"name": "wp_publish_post", "args": {"brief": "news"}},
            {
                "name": "wp_assemble_menu",
                "args": {
                    "menu_name": "Main",
                    "page_refs": ["$ref:step-0:page.id"],
                },
            },
        ]
    )
    steps = await LLMPlanner(llm=llm).plan("build the site nav", "acme")

    menu_step = next(s for s in steps if s.tool == "wp_assemble_menu")
    assert set(menu_step.depends_on) == {"step-0", "step-1"}
