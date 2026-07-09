# WPA companion plugin

`wpa-companion/wpa-companion.php` is a single-file **must-use plugin**: it
registers the exact set of protected post-meta keys this platform writes
(Elementor layout data, Yoast/RankMath SEO fields, our JSON-LD meta) with
`show_in_rest`, so a WP REST API write to those keys actually persists instead
of being silently dropped by WordPress core.

Being an mu-plugin means it auto-loads with no activation step and can't
accidentally be left deactivated — this is infrastructure the platform depends
on, not an optional feature.

## Local dev (Docker sandbox)

`docker-compose.yml` bind-mounts `wpa-companion.php` directly into both the
`wordpress` and `wpcli` services' `wp-content/mu-plugins/` — no manual step
needed beyond `docker compose up`.

## Real client sites

Delivered like any other theme/file-level change, per `AGENTS.md`'s WordPress
integration conventions: upload the file via Fabric/Paramiko to
`wp-content/mu-plugins/wpa-companion.php` on the target site. No WP-CLI
install/activate step is needed (mu-plugins don't go through the plugin
activation flow) — the file existing at that path is sufficient.
