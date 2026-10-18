---
title: Sonarr
container:
  repository: tuxcrate/sonarr
  upstream: https://github.com/Sonarr/Sonarr
  description: >-
    Sonarr is a TV series collection manager for Usenet and BitTorrent users.
    This image runs as a non-root user and packages the upstream self-contained .NET build.
  docker_run:
    - -d
    - --name sonarr
    - '--user "$(id -u):$(id -g)"'
    - --read-only
    - --cap-drop=ALL
    - --security-opt=no-new-privileges:true
    - --tmpfs /tmp:rw,nosuid,nodev
    - -p 127.0.0.1:8989:8989
    - '--mount "type=bind,src=$PWD/config,dst=/config"'
    - '--mount "type=bind,src=$PWD/data,dst=/data"'
    - ghcr.io/tuxcrate/sonarr:latest
  compose:
    services:
      sonarr:
        image: ghcr.io/tuxcrate/sonarr:latest
        user: "${UID}:${GID}"
        read_only: true
        cap_drop:
          - ALL
        security_opt:
          - no-new-privileges:true
        tmpfs:
          - /tmp:rw,nosuid,nodev
        ports:
          - 127.0.0.1:8989:8989
        volumes:
          - ./config:/config
          - ./data:/data
        restart: unless-stopped
---

{% extends "container.md.jinja" %}

{% block prerequisites %}
## Before starting

Create the bind-mount directories as the user that will run Sonarr:

```sh
mkdir -p config data/downloads data/media/tv
export UID GID="$(id -g)"
```

The image defaults to UID/GID `1000:1000`. The examples override this with your
user's IDs. Set `UID` and `GID` in your shell or a Compose `.env` file. There are
no `PUID`/`PGID` variables or root startup scripts; existing bind mounts must
already be writable by the chosen user. A fresh named volume at `/config` uses
the image's default ownership.

Open <http://localhost:8989> and complete Sonarr's authentication setup.
The examples bind to localhost; use an authenticated reverse proxy for remote
access rather than exposing an unconfigured instance to the internet.

### Storage and permissions

Persist `/config`, which contains the database, API key, settings, and logs.
Back it up before upgrading, especially before trying a prerelease. Do not run
stable and develop against the same configuration directory or assume a database
can be downgraded after migration.

Mount downloads and your library together under `/data`. Configure your download
client with the same paths, for example `/data/downloads` and `/data/media/tv`,
and give both applications access to the files. A shared mount allows hardlinks
and atomic moves when the underlying filesystem supports them. Separate mounts
or filesystems may force copies instead.

The image supports a read-only root filesystem with writable `/config`, `/data`,
and `/tmp`, as shown below. It does not need privileged mode or Linux capabilities.

### Release tracks

| Track | Moving tags | Upstream branch |
| --- | --- | --- |
| Stable | `latest`, `4`, `4.0` | `main` |
| Prerelease | `develop`, `preview` | `develop` |

The usage examples select a published image tag from the table below. For
prereleases, select a `develop` release or explicitly use
`ghcr.io/tuxcrate/sonarr:develop`. Prerelease builds never move `latest` or stable
series tags. Exact four-part upstream versions and immutable `-rN` image revisions
are retained.

Update by pulling a newer container image and recreating the container. Sonarr's
in-app updater is disabled for this package.

The container packaging uses AGPL-3.0; Sonarr and its bundled dependencies retain
their upstream licenses. Sonarr's source is available from the
[upstream release tags](https://github.com/Sonarr/Sonarr/tags), matching the
application version shown below.

{% endblock %}
