# Documentation site

A static, multi-page website for Raspberry Pi MQTT Monitor — plain HTML + one CSS file, no build
step. Content is derived from the project `README.md` and `CHANGELOG.md`.

## Preview locally

```bash
python3 -m http.server -d docs 8000
# then open http://localhost:8000/
```

## Publish with GitHub Pages

In the repo **Settings → Pages**, set **Source** to *Deploy from a branch*, choose the `master`
branch and the **`/docs`** folder. The site is served from the root of `/docs` (so `index.html`
is the home page and images resolve from `docs/images/`).

## Structure

- `index.html` — home (intro, features, links)
- `monitoring.html` — what gets monitored
- `installation.html` — install / uninstall
- `cli.html` — CLI reference
- `configuration.html` — config options + display backends
- `home-assistant.html` — HA integration
- `external-sensors.html` — external sensors
- `changelog.html` — release notes
- `assets/styles.css` — shared theme (auto light/dark) and layout
- `assets/nav.js` — mobile sidebar toggle
- `images/` — images used by the pages
