---
title: zrepl
container:
  repository: tuxcrate/zrepl
  topics: [backup, containers, docker, zfs, zrepl]
  upstream: https://github.com/zrepl/zrepl
  description: >-
    zrepl is a ZFS replication tool.
    This image includes the zrepl daemon and Debian ZFS userland utilities.
  docker_run:
    - --rm
    - --name zrepl
    - --device /dev/zfs:/dev/zfs
    - --cap-drop ALL
    - --security-opt no-new-privileges=true
    - '--mount "type=bind,src=$PWD/zrepl.yml,dst=/etc/zrepl/zrepl.yml,readonly"'
    - ghcr.io/tuxcrate/zrepl:latest
  compose:
    services:
      zrepl:
        image: ghcr.io/tuxcrate/zrepl:latest
        devices:
          - /dev/zfs:/dev/zfs
        cap_drop:
          - ALL
        security_opt:
          - no-new-privileges:true
        volumes:
          - ./zrepl.yml:/etc/zrepl/zrepl.yml:ro
---

{% extends "container.md.jinja" %}

{% block prerequisites %}
## Host setup

The image runs as `tuxcrate`, UID/GID `1000:1000`. The host must have the ZFS
kernel module loaded and the relevant pools imported. The container uses the
host's `/dev/zfs`; it does not load modules or import pools.

Before starting the container:

- Make `zrepl.yml` and any mounted credentials readable by UID 1000. Keep secrets
  restricted to that user rather than making them world-readable.
- Allow the container user to open `/dev/zfs` for reading and writing. If the
  device is restricted to a host group, add its numeric GID with `--group-add`
  or Compose `group_add`. Do not make the device world-writable just for this
  container.
- Delegate ZFS permissions to the host UID corresponding to container UID 1000.
  Without user-namespace remapping, this is host UID 1000. Check which host
  account owns that UID before granting access.

For a snapshot/send/prune job, the following is a starting permission set.
Run it as a host administrator, replacing `tank/source` with a dataset selected
by your zrepl configuration:

```sh
sudo zfs allow -u 1000 snapshot,send,destroy,hold,release,bookmark tank/source
```

By default, these permissions apply to the dataset and its descendants.
`destroy` allows destructive operations, so delegate only on datasets this
instance should manage. Jobs that set ZFS properties need the corresponding
property permissions as well. Review the daemon logs for permission failures.

Ensure the host ZFS kernel module includes the fix for
[CVE-2026-79619](https://github.com/openzfs/zfs/security/advisories/GHSA-mhf5-q8gw-qg9v)
before exposing `/dev/zfs` to a user-namespace container. Updating the utilities
inside the image does not fix the host kernel module.

## Non-root operation and limitations

The examples expose only `/dev/zfs`, drop Linux capabilities, and do not use
`--privileged`. ZFS access is controlled by host device permissions and
[`zfs allow`](https://openzfs.github.io/openzfs-docs/man/master/8/zfs-allow.8.html)
delegation. Configuration may also require network ports, credentials, or mounts
for hooks; add these according to your jobs.

Receiving needs additional dataset-creation, receive, and property permissions.
Linux does not support delegation of mounting and certain related operations.
An unmounted backup target may avoid mounting, but receive and pruning behavior
must be tested on a disposable dataset before using this setup for backups.

Running as a non-root user is not the same as running a rootless Docker or Podman
engine. Rootless engines introduce UID/GID mapping, device-access, and ZFS
namespace constraints. Full rootless-engine support has not been verified.

`/var/run/zrepl` and `/home/tuxcrate` are writable by the image's default user.
If you override the user or mount over those directories, provide suitable
ownership yourself. To revert delegation granted by the example above:

```sh
sudo zfs unallow -u 1000 snapshot,send,destroy,hold,release,bookmark tank/source
```

For workloads that still require root, overriding the image user with
`--user 0:0` (Compose `user: "0:0"`) is a compatibility option. Device access and any
required capabilities must be configured separately; changing the user alone
does not provide them.
{% endblock %}
