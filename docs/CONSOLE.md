# The console — what the closet monitor shows

The box has its own screen in the closet. Three things live on it, all
installed by `install.sh`:

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
