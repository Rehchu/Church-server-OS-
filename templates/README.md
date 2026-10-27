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

Image tags are pinned to versions that existed when this was written. Update
them on purpose, not by accident: change the tag, `arisectl app deploy` again.
Where a tag is `:latest` the comment in `compose.yaml` says why.
