# The Store (08)

Bradly's Oct 30 answer H4 replaces the earlier all-template installation:
install **Nextcloud, Vaultwarden, Uptime Kuma, Netdata and File Browser** first.
The other templates stay available in the Store. Every app has resource caps
(round 3, 40); measure actual headroom as well as the configured limits.

## Two tabs

**Installed**: every deployed app with its state, address, CPU and memory,
an **auto** tick (starts with the box), Start/Stop/Restart, Logs, and
Remove (typed name; the containers go, the data folder under
`/srv/arise/apps/<name>` stays, and deleting that is a by-hand decision).
Above the table a gauge shows the sum of the running apps' **container caps**.
The startup budget is physical RAM minus 2048 MiB for core services. This is
headroom in the allocation plan, not a measurement of core-service usage.
Every start, restart, update and autostart enable checks the caps of existing
running/autostart containers, including containers outside the Store. An
uncapped existing container or an unreadable allocation blocks another start.

**Catalogue**: the 26 templates in `templates/` and the 35 entries in
`catalog/catalog.yaml`, one card each with an honest memory estimate, the
cap, the CPU limit, whether it stops itself when idle, and what it does
with the house look. Search and a category filter. Catalogue cards say
"image tag not pulled from this build: verify before first deploy".

## The core set, within the budget

The installer defaults to the five apps above. Choose `--apps all`
explicitly to deploy every template, or `--no-apps` for a
desktop/directory-only rehearsal. Deployment writes Compose with caps,
generates secrets and pulls images; apps are **started only within the
memory budget** and according to their autostart setting. A core app may
therefore be installed but stopped, including File Browser by default.
Each `template.yaml` carries

```yaml
autostart: true        # start with the box
ram_mb: 350            # an honest estimate at rest
limits: {mem_mb: 768, cpus: 1.0}   # the cap written into every service
```

Since round 6 (14), Nextcloud is the Macs' and phones' sync service
(docs/SYNC.md), so a selected sync installation budgets it before optional apps.
`apps.autostart_plan` reserves the required Nextcloud stack first, then takes
optional autostart apps smallest-cap-first until RAM minus 2048 MiB is spent.
It uses each stack's sum of per-service hard caps, never its estimated idle RAM.
Among the selected apps, the rest and everything marked `autostart: false`
(ollama, open-webui, frigate, moodle, synapse, mattermost, kimai, churchcrm,
phplist, nginx-rtmp, wg-easy, filebrowser, every desktop program
and both experiments), are deployed with `docker compose create` and left
stopped, one click away. `arisectl doctor` warns when the autostart caps
exceed the budget. The choice is remembered per app in
`/srv/arise/apps/<name>/arise.json`; `arisectl app autostart <name> on|off`
or the tick in the Store changes it. Enabling autostart checks the memory
budget, writes the restart policy and starts the stack. Disabling autostart
sets Docker's restart policy to `no`; it leaves a currently running stack
running until Stop is pressed. Turn autostart off and stop an unused app to
release its reserved capacity. Docker operations are serialized across the
dashboard and CLI so concurrent starts cannot both claim the same headroom.

## Caps

`apps.inject_limits` writes `mem_limit` and `cpus` into every service of the
Compose file it deploys (a service that sets its own keeps it). The manifest's
limits are per-service defaults; the Store reports the sum of actual service
memory limits. Nextcloud has explicit limits totaling 2688 MiB; Immich totals
5248 MiB. Idle RAM estimates are informative and do not control admission.
Compose supports resource limits without Swarm; these files use its direct
`mem_limit` and `cpus` keys.

Image pulls run one template at a time with Compose parallelism set to one.
Current app and pull progress reach the console and install log, with a bounded
output tail preserved on errors and timeouts. Templates remain available even
when the machine cannot start them all. A custom deployment name is refused:
the templates currently use fixed container names, ports and data paths.

Redeployment reuses the app's `.env`, or its root-only copy under
`/etc/arise/secrets/apps/` after a restore. If data exists but required credentials
are missing, deployment stops before replacing configuration or passwords.

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
has no container image of its own. Check the HP's actual GPU, driver and
streaming performance before choosing games. Off by default.

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
estimated idle usage with machine learning on, with aggregate service caps of
5248 MiB. Store → Immich → Stop stops the whole photo stack. The Store does
not currently offer an ML-only switch.

## arisectl

```
arisectl app list|templates|catalog|deploy <name>|start|stop|restart|update|remove|logs <name>
arisectl app install-all                 every template, started within the budget
arisectl app autostart <name> on|off
arisectl app theme <name>                the house-look plan, the CSS to paste
arisectl app idle-sweep                  what arise-idle-apps.timer runs
```
