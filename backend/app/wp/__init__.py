"""WordPress integration: REST client, WP-CLI executor, and credentials.

Per the project's integration rules:
  - content/pages/media/menus -> WP REST API only
  - installs / activation / cache flush -> WP-CLI only
This package provides the typed wrappers; the LangGraph tools in
``app.agent.tools`` expose them to the agent.
"""
