# The Store (08)

Bradly, round 3, 5: "The 24 app templates should already be preinstalled,
but definitely an App Store for other Linux programs that are free!" And
round 3, 40: cap every app so none can starve the domain or the dashboard.

## Two tabs

**Installed**: every deployed app with its state, address, CPU and memory,
an **auto** tick (starts with the box), Start/Stop/Restart, Logs, and
Remove (typed name; the containers go, the data folder under
`/srv/arise/apps/<name>` stays, and deleting that is a by-hand decision).
Above the table a gauge: the memory **promised** to the running apps (the
sum of their caps) against the box's RAM, with 2 GB always kept for the
domain, Samba, the dashboard and the kiosk.

**Catalogue**: the 26 templates in `templates/` and the 35 entries in
`catalog/catalog.yaml`, one card each with an honest memory estimate, the
cap, the CPU limit, whether it stops itself when idle, and what it does
with the house look. Search and a category filter. Catalogue cards say
"image tag not pulled from this build: verify before first deploy".

## Preinstalled, within the budget

`install.sh` step 6a now runs `arisectl app install-all`: every template is
deployed (compose written with its caps, secrets generated, images pulled),
and **started only within the memory budget**. Each `template.yaml` carries

```yaml
autostart: true        # start with the box
ram_mb: 350            # an honest estimate at rest
limits: {mem_mb: 768, cpus: 1.0}   # the cap written into every service
```

Nextcloud is not in that list: since round 6 (14) it is the Macs' and
phones' sync and starts with the box (docs/SYNC.md).
`apps.autostart_plan` takes the autostart apps smallest-first until RAM
minus 2 GB is spent; the rest, and everything marked `autostart: false`
(ollama, open-webui, frigate, moodle, synapse, mattermost, kimai, churchcrm,
phplist, nginx-rtmp, wg-easy, filebrowser, every desktop program
and both experiments), are deployed with `docker compose create` and left
stopped, one click away. `arisectl doctor` warns when the autostart caps
exceed the budget. The choice is remembered per app in
`/srv/arise/apps/<name>/arise.json`; `arisectl app autostart <name> on|off`
or the tick in the Store changes it.

## Caps

`apps.inject_limits` writes `mem_limit` and `cpus` into every service of the
compose it deploys (a service that sets its own keeps it). Compose's
`deploy.resources` is swarm-only, so these plain keys are used. A
four-container app (Immich) gets the cap on each container.

## The catalogue

`catalog/catalog.yaml`: name, title, description in plain words, category,
a pinned image, ports, volumes under `/srv/arise/apps/<name>/`, env (any
`CHANGE-ME` value becomes a generated secret, root-only copy in
`/etc/arise/secrets/apps/`), `ram_mb`, `limits`, `homepage`, optional
`extra_services` (a database beside the app, written verbatim), optional
`command`, `kind: desktop`, `idle_stop_minutes`, `experimental`, `theme`.
`apps.compose_from_catalog` turns an entry into a compose document; the
main service reads every env key from the app's `.env`. Deploy with the
Store's **Install** or `arisectl app deploy <name>`.

What is in it: Gitea, Paperless-ngx, Stirling PDF, Homepage, Navidrome,
Audiobookshelf, FreshRSS, Linkding, Vikunja, Excalidraw, draw.io,
Calibre-Web, Memos, n8n, ntfy, Gotify, Grafana, Healthchecks, Metabase,
Snipe-IT, Shlink, Umami, SearXNG, Speedtest Tracker, Planka, OnlyOffice
Document Server; the desktop programs below; and two experiments.
Deliberately absent: anything that fights the network the church keeps as
it is (Pi-hole, AdGuard, another DNS or DHCP), and anything that needs a
port forward.

### Desktop programs in a browser tab (Bradly, Oct 28)

GIMP, Inkscape, Krita, Kdenlive, Shotcut, LibreOffice and Audacity from
linuxserver.io's KasmVNC images: the whole program in a window, with
`/srv/arise/shares` at `/shares` and the homes at `/homes` so files save to
the shares; the editors also see the recordings. All `autostart: false`
with `idle_stop_minutes: 60`: `arise-idle-apps.timer` runs
`arisectl app idle-sweep` every 15 minutes, which counts established
connections to each such app's port (`ss`) and stops the app once nobody
has been connected for an hour (`apps.idle_decision`, pinned by the tests).
The Store card says so.

**OnlyOffice Document Server** is in the catalogue, off by default; the
Finder hook that hands .docx/.xlsx/.pptx to it is a later block.

**Game night**: a KDE desktop in a tab (webtop) for the lobby TV, with a
note on installing Heroic Games Launcher and free games inside it; Heroic
has no container image of its own, and the OptiPlex's iGPU limits this to
older 2D titles through a browser stream. Off by default.

**Proclaim under Wine**: an experiment, marked as one (`experimental: true`,
a warning on the card). Proclaim is a .NET/WPF app; expect it not to work;
nothing depends on it; the lobby sign stays Proclaim on a Mac or PC.

## The house look (theme pack)

Every manifest may carry a `theme:` block saying what the app accepts
(`primary`, `logo`, `dark`, `css`, `fonts`, `name`) and how:

| via | what the deploy does |
|---|---|
| `env` | house values merged into the app's env (Grafana: dark theme, the church's name) |
| `files` | files written once under the app's data folder, placeholders filled (Homepage: `settings.yaml`, `custom.css`) |
| `commands` | run through `docker compose exec` after the first start, best effort (Nextcloud: `occ theming:config` name, colour, slogan) |
| `css` | nothing automatic; the Store's **House look** button shows the house CSS with a Copy button for the app's custom-CSS field (Jellyfin, Immich, Owncast) |
| `settings` | a note on which screen takes the values (BookStack, Uptime Kuma) |
| `none` | the card says "keeps its own look" |

House values (`apps.HOUSE`): red `#D6222D`, ink `#0A0A0C`, paper `#F4F2F0`,
Anton for headings and Oswald for text, the flame from `web/icons`, the
church's name and city. `arisectl app theme <name>` prints the plan and the
CSS. Placeholders in a manifest: `{{red}}`, `{{ink}}`, `{{paper}}`,
`{{name}}`, `{{city}}`, `{{fonts}}`, `{{logo_url}}`, `{{css}}`.

## Notes and Photos

**Notes (28)** opens Trilium and **Photos (29)** opens Immich inside a
dashboard window (an iframe with an "Open in a tab" button for an app that
refuses framing). Admins see both; members see them when they are in the
Staff or Media groups (`/api/auth/me` carries the groups). The only app
route a member may call is `/api/apps/open/{trilium|immich}`, which answers
with the address and whether it is running. `templates/immich` is new: the
server, machine learning, redis and the pgvecto-rs postgres, about 2.5 GB
with machine learning on, capped at 4 GB; stop the ML container in the
Store if the box is short and the library keeps working.

## arisectl

```
arisectl app list|templates|catalog|deploy <name>|start|stop|restart|update|remove|logs <name>
arisectl app install-all                 every template, started within the budget
arisectl app autostart <name> on|off
arisectl app theme <name>                the house-look plan, the CSS to paste
arisectl app idle-sweep                  what arise-idle-apps.timer runs
```
