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
