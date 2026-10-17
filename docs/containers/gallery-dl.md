---
title: gallery-dl
container:
  repository: tuxcrate/gallery-dl
  upstream: https://github.com/mikf/gallery-dl
  description: >-
    gallery-dl is a command-line program to download image galleries and collections from several image hosting sites.
  docker_run:
    - --rm
    - '--user "$(id -u):$(id -g)"'
    - '--mount "type=bind,src=$PWD/downloads,dst=/downloads"'
    - ghcr.io/tuxcrate/gallery-dl:latest
    - "'https://example.com/gallery'"
  compose:
    services:
      gallery-dl:
        image: ghcr.io/tuxcrate/gallery-dl:latest
        user: "${UID}:${GID}"
        volumes:
          - ./downloads:/downloads
        command:
          - https://example.com/gallery
---

{% extends "container.md.jinja" %}
