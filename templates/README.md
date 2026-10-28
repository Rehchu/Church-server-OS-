# App templates

Each folder is one app: a `compose.yaml` and a `template.yaml` manifest
(name, description, ports, volumes, env, category, icon). Deploy with

```bash
arisectl app deploy filebrowser --name files
```

or Dashboard → Apps → Templates → **Deploy**. Data for every app lives under
`/srv/arise/apps/<name>/` and the `apps` backup job snapshots it nightly.

| Template | What it is for | Port |
|---|---|---|
| `filebrowser` | a web file manager over `/srv/arise/shares` for anyone with a browser; uses the domain accounts through the share permissions it runs as | 8081 |
| `uptime-kuma` | watches the website, the NAS, the server and the YouTube live page; sends a notification when one goes down | 8082 |
| `syncthing` | keeps a folder on the media Mac and a folder on the server identical, without anyone dragging files | 8384, 22000 |
| `vaultwarden` | the church's own password vault (Bitwarden-compatible apps on every phone and Mac) | 8083 |
| `guacamole` | remote desktop (RDP, VNC, SSH) to any church computer from a browser tab, through the server; the door into the closet from Alexandria, the Hub and home | 8084 |
| `netalertx` | open-source "who is on my network": every device on Netgear A's wire with a presence timeline and an alert when something new appears. The deeper version of the dashboard's Network app; runs on the host network so it can ARP | 20211 |
| `wg-easy` | self-hosted WireGuard VPN with a web page and QR codes; the alternative to native WireGuard (`install.sh --with-wireguard`) and to Tailscale. Never both on 51820 | 51820/udp, 51821 |

Image tags are pinned to versions that existed when this was written. Update
them on purpose, not by accident: change the tag, `arisectl app deploy` again.
Where a tag is `:latest` the comment in `compose.yaml` says why. Guacamole and
wg-easy carry a "verify before first deploy" note because their tags were not
pulled from this build.
