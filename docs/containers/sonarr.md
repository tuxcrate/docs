---
title: sonarr
container:
  repository: tuxcrate/sonarr
  upstream: https://github.com/Sonarr/Sonarr
  description: >-
    Sonarr is a TV series collection manager for Usenet and BitTorrent users.
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
