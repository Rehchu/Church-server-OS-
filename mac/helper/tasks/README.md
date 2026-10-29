# mac/helper/tasks

Extra task scripts the helper calls, one per task kind it hands off.

- `nextcloud.sh`: the `nextcloud` task (round 6, sync). Not here yet; the Nextcloud
  work adds it. The helper calls it as

  ```
  /usr/local/arise/helper/tasks/nextcloud.sh --user <first.last> --local <short name> --server <https://...>
  ```

  `--local` is the macOS account to set the client up in. It is the AD account itself
  for a mobile account, or the local account an admin chose to Link (it stays as it is
  and signs in to the server's files as `--user`). Exit 0 means done; any other exit is
  reported as failed, with the script's last output line as the reason. Until the script
  exists, the helper reports the task as skipped, and the server queues it again when an
  admin re-runs it.

enrol.sh downloads `nextcloud.sh` from `/mac/nextcloud.sh` when the server has it.
