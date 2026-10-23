---
title: radarr
container:
  repository: tuxcrate/radarr
  topics: [containers, docker, movie-manager, radarr]
  upstream: https://github.com/Radarr/Radarr
  description: >-
    Radarr is a movie collection manager for Usenet and BitTorrent users.
  docker_run:
    - -d
    - --name radarr
    - --read-only
    - --cap-drop=ALL
    - --security-opt=no-new-privileges:true
    - --tmpfs /tmp:rw,nosuid,nodev
    - -p 127.0.0.1:7878:7878
    - --mount type=volume,src=radarr-config,dst=/config
    - --mount type=volume,src=radarr-data,dst=/data
    - ghcr.io/tuxcrate/radarr:latest
  compose:
    services:
      radarr:
        image: ghcr.io/tuxcrate/radarr:latest
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
          - radarr-config:/config
          - radarr-data:/data
        restart: unless-stopped
    volumes:
      radarr-config:
      radarr-data:
---

{% extends "container.md.jinja" %}
