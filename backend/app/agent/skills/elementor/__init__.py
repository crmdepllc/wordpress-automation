"""Elementor page-generation skill.

Turns a plain-language brief into valid Elementor ``_elementor_data`` via a
constrained intermediate representation (``PageSpec``) that a deterministic
builder compiles from the real section templates in ``examples/``. Claude never
emits the fragile JSON directly — it only fills the IR — which is how this
skill honors the rule that Elementor JSON is never hand-written from assumption.
"""

from app.agent.skills.elementor.schema import PageSpec, SectionSpec
from app.agent.skills.elementor.skill import (
    ElementorValidationError,
    build_and_validate,
    generate_elementor_page,
    generate_page_spec,
)

__all__ = [
    "PageSpec",
    "SectionSpec",
    "generate_elementor_page",
    "generate_page_spec",
    "build_and_validate",
    "ElementorValidationError",
]
