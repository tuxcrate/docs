# Adding a repository

Use this checklist when contributing a new Tuxcrate repository. Detailed release,
Renovate, infrastructure, and website behavior lives in the linked maintainer
guides. Keep repository READMEs short: the project name, a brief description,
and a documentation link.

## Establish the requirements

Before scaffolding a container repository, agree on:

- Name, visibility, upstream project URL, and a short description of what the
  application does. Use `tuxcrate/<name>` and `ghcr.io/tuxcrate/<name>` unless
  another destination is needed.
- Homepage URL: normally `https://tuxcrate.com/containers/<name>/`.
- Upstream license, redistribution requirements, and corresponding-source access.
  New packaging repositories use AGPL-3.0 unless another license is agreed.
  Include its full text in `LICENSE`; preserve upstream licenses and notices
  separately in the image.
- Installation source and exact upstream version. Confirm that packages or
  binaries exist for both `linux/amd64` and `linux/arm64`; finding one asset
  does not establish availability for both architectures.
- Base-image tag and multiarchitecture manifest digest, verified against the
  registry. Do not reuse an unrelated digest from another repository.
- Runtime requirements: user, writable directories, configuration, ports, mounts,
  capabilities, and host dependencies.

Start with one stable track. Add prereleases or older maintained tracks only
when requested and supported upstream. Repository creation, pushes, GitHub
settings, infrastructure applies, and image publication require maintainer
approval; they are not validation steps.

## Scaffold the container repository

The normal layout is:

```text
.github/workflows/container.yml
.dockerignore
Containerfile
LICENSE
README.md
meta.yaml
renovate.json
tests/smoke.sh
```

Add dependency files and helper scripts only as needed. Use
[gallery-dl](https://github.com/tuxcrate/gallery-dl) as a PyPI reference,
[zrepl](https://github.com/tuxcrate/zrepl) for APT installation, and
[Lidarr](https://github.com/tuxcrate/lidarr) or
[Sonarr](https://github.com/tuxcrate/sonarr) for GitHub releases. Read the files
you reuse; do not copy application-specific paths, ports, pins, or Git history.

Keep `.git`, workflows, README, metadata, Renovate configuration, and host-side
tests out of the Docker build context unless the build actually needs them.
Host-side tests still count as release inputs even when excluded by
`.dockerignore`; see [the release-input comparison](container-releases.md#skipping-unchanged-releases).

### Release metadata and dependency updates

Declare every track in root `meta.yaml`. Build settings belong there, not in
workflow inputs. Each track needs a quoted exact version, a complete `baseImage`
reference with tag and verified digest, and explicit tags. Use `upstream`
discovery metadata so Renovate can update the application pin.

Stable tags normally include `${version}` and `latest`, with numeric series
aliases where useful. Numeric upstream prereleases need `prerelease: true` and
a suffixed image-version tag such as `${version}-prerelease`. They must not own
`latest` or unsuffixed numeric series aliases.

Metadata does not install the application. The Containerfile must configure the
package source or release download itself. Keep pins in metadata rather than
duplicating them in the Containerfile. Avoid extra `buildArgs` unless installation
genuinely needs another input. For branch-specific assets, use upstream release
metadata to select and verify the matching branch when possible.

Follow the [metadata schema and tag rules](container-releases.md#required-root-metadata-and-release-tracks)
and [image Renovate preset](dependency-updates.md#container-image-repositories).
Add local Renovate rules only for application-specific version formats or
release channels.

### Installation and runtime

Use the shared build-argument contract:

```dockerfile
ARG BASE_IMAGE
FROM ${BASE_IMAGE}

ARG APP_VERSION
```

Require `APP_VERSION` and install it exactly: `package==${APP_VERSION}` for PyPI,
`package=${APP_VERSION}` for APT, or the pinned release asset. Map download
architectures explicitly and verify checksums or signatures when provided. For
channel-specific downloads, check that the asset agrees with the upstream
release's channel.

Keep version, dependency, and installation assertions in the build. Do not start
a service during the build to test readiness; test the finished image through
the [host-side runtime smoke hook](container-tests.md).

Use user and group `tuxcrate` with UID/GID `1000:1000` when the application supports
non-root execution. For an Alpine service using `/config`, the account-creation
fragment is:

```dockerfile
RUN addgroup -g 1000 tuxcrate \
    && adduser -D -u 1000 -G tuxcrate -h /config -s /sbin/nologin tuxcrate \
    && mkdir -p /config \
    && chown 1000:1000 /config

USER 1000:1000
WORKDIR /config
```

Adapt the home and working directory to the application; CLI tools may use
`/home/tuxcrate` instead. Set a suitable entrypoint and default command, make
required directories writable, and retain valid OS identification in the final
image. Root-required applications must document why and declare
`com.tuxcrate.runtime-user="root"`, as described in
[shared runtime-user validation](container-tests.md#shared-runtime-user-validation).
The label does not grant host privileges.

The shared validator owns user/group identity checks. Repository smoke hooks own
application behavior and directory permissions. Use only
`com.tuxcrate.smoke-test` for test-container labels and clean up on exit. Never
pass credentials through build arguments or write them into images.

### Workflows

Add the [shared container caller](container-releases.md#calling-the-workflow).
Do not duplicate shared build, test, or publishing jobs. Keep `uses` and
`shared-ref` coordinated when pinning shared tooling.

PRs test all active tracks and platforms without moving production aliases.
Same-repository PRs publish retained `pr-` tags into the production package;
there is no automatic preview cleanup. Reserve this prefix for PR builds.
Default-branch pushes can publish real releases. For an empty repository,
a README-only default branch followed by a container PR keeps the first
publication behind review. Do not push release workflows to the default branch
as a supposed dry run.

## Add the website page and GitHub configuration

In `tuxcrate/docs`, add `docs/containers/<name>.md` using the
[container-page format](website.md#image-pages). Provide the upstream URL,
description, topics, and independently verified Docker CLI and Compose examples.
Document required directories, ownership, configuration, capabilities, and host
dependencies before offering runnable examples.

Add fictional offline fixture coverage. Release tables are generated from GitHub
assets and verified GHCR tags; do not hand-maintain them. Coordinate live page
deployment with accessible release data.

With approval, register the repository in `tuxcrate/.github` infrastructure and
follow the [GitHub infrastructure guide](github-infrastructure.md). Import
existing repositories before managing them through OpenTofu. Set and verify the
GitHub About description and homepage, enable Renovate, and require
`container / pull-request-check` before merging container changes.

Verify GHCR visibility and Actions write access for the shared production and
preview package. Do not assume a workflow token makes a newly created package public.

## Validate and submit

Before requesting review:

1. Validate `meta.yaml` with the shared `container-release plan` command, not
   only a generic YAML parser. Build the CLI in `tuxcrate/github-actions`, then
   run it from the image repository with `GITHUB_REPOSITORY=tuxcrate/<name>` and
   a temporary `GITHUB_OUTPUT` path. Do not use `reserve`: it creates a real
   draft release.
2. Run `actionlint` and
   `renovate-config-validator --strict --no-global renovate.json` when available.
3. Build every active track uncached for both target platforms. Supply the planned
   `BASE_IMAGE` and `APP_VERSION`, `--pull --no-cache`, and
   `--build-arg BUILDKIT_DOCKERFILE_CHECK=skip=InvalidDefaultArgInFrom`. Validate
   finished images through the [shared artifact test and runtime hooks](container-tests.md#local-validation).
   Report missing tooling or architecture support rather than claiming tests
   passed.
4. Run the [website checks and a clean strict offline build](website.md#local-development)
   for docs changes. Review the diff for copied names, placeholders, duplicated
   pins, and credentials.

Use Conventional Commits for commits and PR titles, such as
`feat: add example container` or `docs: add example container page`. Keep changes
in the repositories they belong to; the workspace parent is not a Git repository.
Publish shared tooling changes before callers depend on them.

After the approved first release, verify public pulls, both platforms, immutable
revision tags, moving aliases, the GitHub release, and `release.json`. Check
documented runtime examples and preview visibility separately. Report files
changed, checks performed, and remaining configuration or publication steps.
Do not claim publication merely because a workflow was added.

## Non-container repositories

Use the general `github>tuxcrate/renovate-config` preset, keep the README short,
and add only the CI and documentation the project needs. Do not add container
metadata or release workflows to repositories that do not publish images.
