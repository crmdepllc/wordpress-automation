"""Celery worker for long-running orchestration execution.

Scaffolding in Sprint 4: the deliverable's execute phase runs inline (so it
streams live), but this worker can resume a persisted task off the request path
for genuinely long jobs. It reads the same Postgres checkpoint, so it operates
on exactly the task the API paused.
"""
