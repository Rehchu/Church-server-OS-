# The everyday apps and the desktop (v0.8 "Exodus", Fork A)

What Windows 11 and macOS have for the ordinary day, built into ariseOS from
Bradly's round-3 answers (docs/ANSWERS.md). Numbers in brackets are the
answers. Nothing here invents church data: the sample events say "sample",
the weather comes from Open-Meteo or says it is offline, the verse text comes
from the Bible source.

## Calendar (app 20) and the feed (10)

One church calendar on the server. The services (Sunday 10:30 Pineville,
10:00 Alexandria, Monday 19:00 Glory Night) come from `[church]` in
`arise.toml` and are generated, never stored. Events are added by
administrators in the app (title, start, end, where, note) and kept in
`/var/lib/arise/calendar.json`; removing one asks for the word `remove`.
Members read.

**Subscribe** shows the address every Mac and phone can take:

```
webcal://arise-server/calendar.ics
```

The feed is at `GET /calendar.ics` and `GET /api/public/calendar.ics` with no
login, `text/calendar`, an `America/Chicago` VTIMEZONE, each service as a
weekly `RRULE`, each event as a `VEVENT`, lines folded at 75 octets. Apple
Calendar: File → New Calendar Subscription. iPhone: Settings → Calendar →
Accounts → Add Account → Other → Add Subscribed Calendar. Away from the
building the phone needs Tailscale on first. Notification Center shows the
week's items under the month.

Routes: `GET /api/calendar?year&month`, `GET /api/calendar/subscribe`,
`POST /api/calendar`, `PUT /api/calendar/{id}`, `DELETE /api/calendar/{id}`
(admin). Server: `server/arise_server/calendar.py`.

## Weather (13)

`GET /api/weather`: Open-Meteo for Pineville (31.32, -92.43), Fahrenheit,
today and five days, cached thirty minutes on the server, no key. The widget
sits on the desktop and in Notification Center. When the fetch fails the
answer is `{ok: false, why}` and the widget says "No weather (offline)";
nothing is invented. `weather.summary()` gives one line for a morning report.

## Calculator (21) and Clock (22) (14)

The Calculator is a safe evaluator (no `eval`): `+ − × ÷ % ^` and brackets,
unary minus as on paper (`-3^2` is `-9`), keyboard and buttons. Type a sum
into Spotlight and the answer is the first row; Enter copies it and opens the
app. The Clock has a world clock (Pineville, New York, Los Angeles,
Jerusalem), a timer with presets and a quiet chime at zero, a stopwatch with
laps, and an alarm that rings on the screen while the page is open (it is
not a phone alarm, and the app says so).

## Help (23) (35)

The repository's docs rendered inside the dashboard: `GET /api/help` lists
them, `GET /api/help/{name}` renders one, `?q=` searches the text. Members
see only `docs/PORTAL-GUIDE.md`; administrators see README and every
`docs/*.md` except the question sheet and the wipe checklist. Rendering is
python-markdown (`markdown>=3.5`) with every `<` escaped first, so a doc can
never put a tag or a script into the page. F1 or ⌘? opens Help; ⌘/ opens the
keyboard-shortcut sheet; the Help menu has both.

## What's New (34)

`CHANGELOG.md` at the repository root. `GET /api/about/whatsnew` returns the
top section, ten lines at most; About shows it, and after the version changes
every browser gets one toast pointing at About (remembered per browser).

## The password meter and the rules (36)

`GET /api/me/password/rules` reads `samba-tool domain passwordsettings show`
and says only what the domain reports: the length, complexity (three of the
four kinds, not your name), history if set, expiry. The change-password window
lists those rules, shows a strength meter as you type, and refuses a new
password shorter than the domain's minimum before the server does.

## The power menu (31)

The flame menu, administrators only: Restart the dashboard, Restart the
domain, Restart…, Shut Down…, each behind a typed confirmation. The server
refuses all of it during a service (`church.in_service_now`: from a service's
start until two hours after) and says when the service ends. The domain
restart is refused the same way through `/api/services/samba-ad-dc.service/restart`.

## Snap windows (19)

Drag a window to the left or right edge for that half, to a corner for a
quarter, to the top to fill the screen; a red ghost shows where it will land.
⌘← ⌘→ ⌘↑ tile the focused window, ⌘↓ puts it back (or minimises it if it was
not snapped). Dragging a snapped window gives it its old size back. Not on
phones. On a Windows keyboard Ctrl does what ⌘ does.

## Accessibility (32)

Control Center: Larger text, Reduce motion, High contrast, remembered per
browser. Reduce motion also honours the system setting and switches off the
dock zoom. Menus take the arrow keys and Enter; Tab reaches every control;
Escape closes whatever is open; focus rings are visible.

## The Dock (round 4)

The Dock hides: it slides below the edge and comes back when the mouse
touches the bottom of the screen, when an app opens, or when it has the
keyboard focus. A switch in Control Center keeps it on screen instead. The
administrator's default set is Finder, Overview, Sunday, Sermons, Calendar,
Mail, Store, Settings, Terminal; members get Finder, Sermons, Bible, Sunday,
Calendar, Assistants, Help. Right-click an icon in the Dock or in Launchpad
to keep it or remove it; an open app shows in the Dock while it is open
either way. Pins are per browser (PREF).

## The greeting, the lock screen, the sign-in screen (round 4)

After sign-in a three-second toast: "Good morning, Bradly. Today: Romans
8:28." (the day's verse reference), once per browser session, never on the
monitor. The lock screen and the sign-in screen carry "Arise Church ·
Pineville" and the next service; the sign-in screen reads it from the public
signage feed, so it needs no login.
