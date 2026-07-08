"""Sprint 8 eval suite: a scored golden dataset across every skill.

Each skill contributes a list of ``Scenario`` objects (see ``scoring.py``).
``runner.run_all()`` executes them all offline (LLM/generators mocked, no
Docker) and produces a ``SkillReport`` per skill; ``report.py`` renders those
into the markdown/JSON used by both ``pytest`` (local dev loop) and
``scripts/run_evals.py`` (the CI gate) — one scoring engine, two callers.
"""
