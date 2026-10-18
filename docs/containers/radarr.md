---
title: radarr
container:
  repository: tuxcrate/radarr
  upstream: https://github.com/Radarr/Radarr
  description: >-
    Radarr is a movie collection manager for Usenet and BitTorrent users.
  docker_run:
    - -d
    - --name radarr
    - '--user "$(id -u):$(id -g)"'
    - --read-only
    - --cap-drop=ALL
    - --security-opt=no-new-privileges:true
    - --tmpfs /tmp:rw,nosuid,nodev
    - -p 127.0.0.1:7878:7878
    - '--mount "type=bind,src=$PWD/config,dst=/config"'
    - '--mount "type=bind,src=$PWD/data,dst=/data"'
    - ghcr.io/tuxcrate/radarr:latest
  compose:
    services:
      radarr:
        image: ghcr.io/tuxcrate/radarr:latest
        user: "${UID}:${GID}"
        read_only: true
        cap_drop:
          - ALL
        security_opt:
          - no-new-privileges:true
        tmpfs:
          - /tmp:rw,nosuid,nodev
        ports:
          - "127.0.0.1:7878:7878"
        volumes:
          - ./config:/config
          - ./data:/data
        restart: unless-stopped
---

{% extends "container.md.jinja" %}

{% block prerequisites %}
Create the bind-mount directories as the user who will run Radarr:

```sh
mkdir -p config data/downloads data/movies
```

The examples run Radarr with your UID and GID. That user must be able to write
to `config`, `data/downloads`, and `data/movies`. The image defaults to UID/GID
`1000:1000` when no user override is supplied; it does not change bind-mount
ownership at startup. To use existing directories, adjust their permissions
for the chosen user first.

For Compose, create a `.env` file beside `compose.yaml` before starting it:

```sh
printf 'UID=%s\nGID=%s\n' "$(id -u)" "$(id -g)" > .env
```

Radarr needs a separately configured Usenet or BitTorrent download client and
indexers. Give the download client access to the same downloads directory,
ideally at the same `/data/downloads` path. Keep downloads and movies on the
same filesystem under `/data` if you want hardlinks and atomic moves.
{% endblock %}

{% block details %}
## Configuration

Open <http://localhost:7878> and complete Radarr's initial setup, including
authentication, indexers, and the download client. Set the movie root folder to
`/data/movies`. The examples bind the web interface to host loopback only; use
an authenticated reverse proxy or another deliberate network configuration
for remote access.

Configuration, the database, and logs persist in `/config`. Media and downloads
live under `/data`; back up `/config` before upgrading. The root filesystem can
remain read-only with writable `/config`, `/data`, and `/tmp`, as shown above.
No extra capabilities or privileged mode are required. `PUID` and `PGID`
environment variables are not supported; use Docker's `--user` or Compose's
`user` setting instead.

Radarr's built-in updater is disabled. Pull a newer image and recreate the
container to update it.

## Licensing and source

The packaging repository is MIT-licensed. Radarr is GPL-3.0 software; its
upstream license and bundled notices remain in `/opt/radarr`. The image's
`/usr/share/doc/radarr/SOURCE` file links to the exact upstream release and
corresponding source archive used for that build.
{% endblock %}

{% block tags %}
## Choosing a tag

This image follows Radarr's stable `master` releases. `latest`, the major tag,
and the major/minor tag follow the current stable image. The exact application
version follows rebuilds of that version; use an immutable `-rN` revision tag
from the version table when you need a fixed release. There is no prerelease
track.
{% endblock %}
