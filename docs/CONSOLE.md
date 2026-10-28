# The console — what the closet monitor shows

The box has its own screen in the closet. With `install.sh --kiosk` that
screen **is the Arise desktop**: the same macOS-style shell the dashboard
shows a browser (Finder, menu bar, dock, widgets, Spotlight), full screen on
tty1 from the moment the box has booted. Everything below the next section is
the text fallback.

## The boot splash

ariseOS boots like a product: ink, the flame breathing in, a thin red
progress bar, the name in small caps, no Linux text (answer 1: a splash,
no sound). It is a Plymouth theme, `config/plymouth/ariseos`, whose
pictures are drawn by `scripts/gen-plymouth-art.py` with no image library;
the installer sets it as the default, rebuilds the initramfs, and tells the
kernel `quiet splash loglevel=3` with a one-second GRUB menu
(`/etc/default/grub.d/60-ariseos.cfg`). Boot messages that matter (a disk
check, a slow unit) appear in small bone text under the bar instead of
scrolling. `install.sh --no-splash` leaves the text boot; deleting the
grub.d file and running `update-grub` brings it back later. Hold Shift at
power-on for the GRUB menu when something has to be chosen.

## The desktop on the monitor (`--kiosk`)

`arise-kiosk.service` starts `cage` (a one-window Wayland compositor, no
desktop environment underneath) running Epiphany in application mode, pointed
at `http://127.0.0.1:4147/?kiosk=1`, as the unprivileged user `arise-kiosk`
(uid 1501, groups `video`, `input`, `render`). It waits for `arise-web` to
answer `/api/health` before it draws anything, so the first thing on screen is
the login window, never a browser error.

In kiosk mode the page hides the pointer after a few idle seconds, locks
itself after ten idle minutes (the lock screen: the clock, the flame, the
password), and never shows a URL bar or a tab. The sign-in is the dashboard's
own admin login; signing out brings the login window back.

```bash
sudo bash /opt/arise/installer/install.sh --kiosk     # add it to an existing install
sudo systemctl status arise-kiosk                       # is it up
sudo systemctl disable --now arise-kiosk; sudo systemctl start getty@tty1   # back to a text login
```

The keyboard on the closet monitor is a Windows one. The desktop knows: every
shortcut takes **Ctrl** where a Mac takes ⌘ (Ctrl+Space Spotlight, Ctrl+W
close, Ctrl+Alt+Q lock), the menus print those labels, and the Windows key
also works where the browser reports it as ⌘.

After five idle minutes the monitor shows the screensaver (clock, next
service, verse of the day, the channel's art); ten minutes, the lock. The
Assistants app opens Claude, ChatGPT, Grok, YouTube Studio or StreamYard
in their own windows on the monitor, signed in with your own accounts; close
the window to return to the desktop. A lobby screen anywhere shows
`http://arise-server:4147/signage` with no login.

**Alt+F2** is a normal text login at any time; **Alt+F1** goes back to the
desktop. `--kiosk` and `--console` conflict on tty1 (both units declare it);
the installer enables whichever was asked for last, and `arisetui` still works
from any login or over SSH.

Needs a monitor that stays plugged in and a GPU the kernel can drive, which
every OptiPlex has. If `cage` cannot start (no `/dev/dri`, a headless build)
the unit fails and tty1 falls back to the banner; `journalctl -u arise-kiosk`
says why.

## The text console

Three things live on it, all installed by `install.sh`:

| What | File | When you see it |
|---|---|---|
| **The banner** | `config/console/issue` → `/etc/issue` | before anyone logs in: the flame, the host name, the dashboard address, the two commands worth knowing |
| **The login message** | `config/console/50-arise-motd` → `/etc/update-motd.d/` | after a login: the flame and `arisectl info` for this box. Ubuntu's own ad lines are switched off |
| **`arisetui`** | `cli/arisetui` → `/usr/local/bin/arisetui` | when you run it, or all day on tty1 with `install.sh --console` |

## arisetui

A curses dashboard like Monolith's `mntui`, in the church's red on black.
Read only. Keys:

```
1 overview    live CPU, memory, disks · needs you · the box · tonight's timetable
2 services    every unit that matters, green or red
3 backups     repository, last run per job, the reason for a failure
4 automator   last run, quota, token, holds, the latest report
5 directory   domain health, users, joined computers
q             quit (not in kiosk mode)
```

It reads the same Python modules as the dashboard and the CLI, so the three
never disagree. It works in any terminal, including over SSH.

## The tty1 dashboard

`install.sh --console` enables `arise-console.service`, which replaces the
login prompt on tty1 with `arisetui --kiosk`: it never exits to a shell, so a
glance at the monitor says whether the box is well and nobody can type into a
root shell left open in a closet. **Alt+F2** is a normal login. To turn it off:

```bash
sudo systemctl disable --now arise-console.service
sudo systemctl start getty@tty1
```
