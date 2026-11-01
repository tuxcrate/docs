---
title: lidarr
container:
  repository: tuxcrate/lidarr
  topics: [containers, docker, lidarr, music-manager]
  upstream: https://github.com/Lidarr/Lidarr
  description: >-
    Lidarr is a music collection manager for Usenet and BitTorrent users.
  docker_run:
    - -d
    - --name lidarr
    - '--user "$(id -u):$(id -g)"'
    - --read-only
    - --cap-drop=ALL
    - --security-opt=no-new-privileges:true
    - --tmpfs /tmp:rw,nosuid,nodev
    - -p 127.0.0.1:8686:8686
    - '--mount "type=bind,src=$PWD/config,dst=/config"'
    - '--mount "type=bind,src=$PWD/data,dst=/data"'
    - ghcr.io/tuxcrate/lidarr:latest
  compose:
    services:
      lidarr:
        image: ghcr.io/tuxcrate/lidarr:latest
        user: "${UID}:${GID}"
        read_only: true
        cap_drop:
          - ALL
        security_opt:
          - no-new-privileges:true
        tmpfs:
          - /tmp:rw,nosuid,nodev
        ports:
          - 127.0.0.1:8686:8686
        volumes:
          - ./config:/config
          - ./data:/data
        restart: unless-stopped
---

{% extends "container.md.jinja" %}

{% block prerequisites %}
Create the configuration and data directories before starting the container:

```sh
mkdir -p config data
```

The selected user must have write access to both directories. Mount your music
library and downloads under `/data`, using the same paths in your download client.

For Compose, set `UID` and `GID` in your project's `.env` file to the values from
`id -u` and `id -g`.
{% endblock %}
