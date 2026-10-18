---
title: prowlarr
container:
  repository: tuxcrate/prowlarr
  upstream: https://github.com/Prowlarr/Prowlarr
  description: >-
    Prowlarr manages and syncs Torrent and Usenet indexers across your media apps.
  docker_run:
    - -d
    - --name prowlarr
    - --read-only
    - --cap-drop=ALL
    - --security-opt=no-new-privileges:true
    - --tmpfs /tmp:rw,nosuid,nodev
    - -p 127.0.0.1:9696:9696
    - --mount type=volume,src=prowlarr-config,dst=/config
    - ghcr.io/tuxcrate/prowlarr:latest
  compose:
    services:
      prowlarr:
        image: ghcr.io/tuxcrate/prowlarr:latest
        read_only: true
        cap_drop:
          - ALL
        security_opt:
          - no-new-privileges:true
        tmpfs:
          - /tmp:rw,nosuid,nodev
        ports:
          - "127.0.0.1:9696:9696"
        volumes:
          - prowlarr-config:/config
        restart: unless-stopped
    volumes:
      prowlarr-config:
---

{% extends "container.md.jinja" %}

{% block prerequisites %}
The examples use a Docker-managed volume for configuration, databases, and logs.
Docker creates it on first use. The image runs as UID/GID `1000:1000` without
additional Linux capabilities or host services.

If you replace the volume with a bind mount, create the host directory first and
give UID/GID `1000:1000` write access. Prowlarr does not need access to your media
or download directories.
{% endblock %}

{% block details %}
## Configuration

Open <http://localhost:9696> on the Docker host and configure authentication before
adding your indexers. The examples bind the port to the host's loopback interface.
For remote access, use an SSH tunnel or a trusted reverse proxy with HTTPS.

Add Sonarr, Radarr, or another supported application under **Settings → Apps**.
Prowlarr and the application must be able to reach each other's configured URLs;
`localhost` inside a container refers to that container, not another application
or the Docker host. For containers on a shared Docker network, use their service
names and internal ports.

Keep `/config` persistent and back it up. The examples use a read-only root
filesystem with writable `/config` and `/tmp`. Update by pulling a new image and
recreating the container; in-application updates are disabled.

## Licensing

The container packaging is licensed under AGPL-3.0. Prowlarr retains its GPL-3.0
license at `/opt/prowlarr/LICENSE`; `/usr/share/doc/prowlarr/SOURCE` links to the
matching upstream source and release.
{% endblock %}

{% block tags %}
## Choosing a tag

`latest` and unsuffixed version tags follow stable releases from Prowlarr's
`master` channel. The prerelease track follows `develop` releases and uses
`-prerelease` suffixes on its exact-version, major, and major/minor tags.

Prereleases never move `latest`. When stable is newer than the configured
prerelease, that prerelease track is skipped until a newer upstream release is
available. Existing prerelease tags remain available but stop receiving rebuilds.
Back up `/config` before switching channels; a newer version may migrate the
database in ways an older version cannot read.
{% endblock %}
