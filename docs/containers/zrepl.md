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
    - --privileged
    - '--mount "type=bind,src=$PWD/zrepl.yml,dst=/etc/zrepl/zrepl.yml,readonly"'
    - ghcr.io/tuxcrate/zrepl:latest
  compose:
    services:
      zrepl:
        image: ghcr.io/tuxcrate/zrepl:latest
        privileged: true
        volumes:
          - ./zrepl.yml:/etc/zrepl/zrepl.yml:ro
---

{% extends "container.md.jinja" %}
