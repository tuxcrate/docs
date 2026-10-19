# Container releases

The shared GitHub Actions workflows for Tuxcrate container images live in [`tuxcrate/github-actions`](https://github.com/tuxcrate/github-actions).
Commands and paths on this page are relative to that repository unless noted.

## Calling the workflow

Call `.github/workflows/container.yml` from an image repository:

```yaml
name: Container
on:
  pull_request:
  push:
    branches: [main]
  schedule:
    - cron: '23 4 * * 1'
  workflow_dispatch:

permissions:
  contents: read

jobs:
  container:
    permissions:
      contents: write
      packages: write
      pull-requests: write
    uses: tuxcrate/github-actions/.github/workflows/container.yml@main
```

Every caller repository must contain `meta.yaml` in its root, even for single-track images.
The workflow checks for this file before building the release tooling.
It then validates the tracks and aliases before building or publishing any images.
There is no configurable metadata path or workflow-version fallback.

The `Containerfile` receives each track's exact version pin as `APP_VERSION`.
It must pin the application to that version and run its own build-time smoke tests.
Keep the version or full APT package pin in `meta.yaml` and update it through a reviewed PR.

### Shared tooling and integration inputs

Image build settings come only from `meta.yaml`.
Workflow inputs cannot set them.
All repositories use the same defaults: `ghcr.io/<caller repository>`, context `.`, root `Containerfile`, and `linux/amd64,linux/arm64`.
Metadata can override these for individual tracks; the caller workflow stays the same.

| Input | Default | Purpose |
| --- | --- | --- |
| `shared-ref` | `main` | Shared tooling ref; must match the workflow's `uses` ref |
| `docs-repository` | Empty | Optional `owner/repo` to notify with an `image-published` repository dispatch |

For a pinned integration, use the same commit SHA in the workflow's `uses` and `shared-ref`.
Both repositories must be accessible to the caller.
For private repositories, configure GitHub Actions access to the shared workflow and shared tooling checkout; the normal caller token cannot check out a different private repository.
The current setup assumes this shared repository is public.

### GitHub API requests during builds

The shared workflow passes the job's `GITHUB_TOKEN` as an optional BuildKit
secret named `github_token` for production and same-repository PR builds.
Containerfiles can mount `/run/secrets/github_token` and use it to authenticate
GitHub API requests. Do not use shell tracing (`set -x`) when reading the secret
or sending the authorization header. Never pass the token as a build argument,
copy it into an image, or write it to a persistent file.

BuildKit does not persist the secret mount in image layers, but the Containerfile
can read and transmit the token. Only trusted contributors should have access to
same-repository branches. Fork PRs receive no token and use unauthenticated
requests, as do local builds without a secret. PyPI/APT Containerfiles need no
changes and do not mount the secret.

For local authenticated builds, add
`--secret id=github_token,env=GH_TOKEN` to the normal Buildx invocation, with
`GH_TOKEN` set in the Docker client's environment, for example using
`GH_TOKEN="$(gh auth token)" docker buildx build ...`.

### Behavior and tags

- PRs build both platforms using QEMU.
  Same-repository PRs publish test images to a separate `ghcr.io/<caller repository>-pr` package; fork PRs remain build-only, with no registry login.
  PRs never create GitHub releases or update production aliases.
  The Containerfile's `RUN` assertions execute on both architectures; no host ZFS kernel module is needed for zrepl's smoke tests.
- Default-branch pushes, schedules, and manual runs rebuild without layer cache, pull the configured base image reference, and publish to GHCR using `GITHUB_TOKEN`.
  A digest-pinned base stays fixed until a source update (such as a Renovate digest-update PR) is merged.
- Outside PR previews, other branches and other event types cannot publish.
  Do not add `pull_request_target` as a publishing trigger.
- An upstream version starts at `0.7.0-r0`; each rebuild increments the image revision.
  `0.7.1` starts again at `0.7.1-r0`.
- The revision tag never moves.
  The track's explicitly configured `tags` move to its new image revision.
  For example, tags `["${version}", "${major}.${minor}", latest]` publish `0.7.0`, `0.7`, and `latest` for `0.7.0`.
  Prereleases may use named aliases such as `preview`, never stable aliases.
  Multiple current releases can share the same default branch through tracks.
- The image is first uploaded by digest, with BuildKit provenance and an SBOM, so failed builds never publish named release tags.
- A draft GitHub release reserves the next revision before tagging the image.
  Successful publication publishes the release, creating `v0.7.0-rN` at the exact source commit.
  GitHub release notes contain the digest, platforms, and linked packaging commits since the previous published image release.
- The release CLI lists all new commit subjects with commit links, oldest first, using `git log`.
  Conventional Commits are not required.
  The first release includes all history; rebuilds without new commits are identified explicitly.
- All releases are serialized across trigger types.
  Revision selection includes both Git tags and all GitHub releases, including drafts and paginated history.
- Stale default-branch runs fail before reserving a revision, preventing aliases from moving backwards.
  Start a fresh run on the current branch HEAD.
- Each release includes a versioned `release.json` asset with the image, track, application version, revision, digest, source commit, platforms, and historical aliases.
  It also includes `os_flavor` (such as `alpine` or `debian`) and `os_version`, read from the final image by digest on the first declared platform, not inferred from the base image tag.
  These use `ID` and `VERSION_ID` from `/etc/os-release` (falling back to `/usr/lib/os-release`); Debian uses `/etc/debian_version` when available to include the point release, such as `13.7`.
  The image's entrypoint is not run. Missing or invalid OS identifiers fail metadata generation rather than publishing guessed values.
  PR builds generate a temporary, synthetic `release.json` using the same metadata generation and validation as real releases, including for fork PRs that cannot publish images.
  Validation checks all required fields, including OS metadata from a locally loaded image of the first declared platform. Empty or invalid required values fail the job.
  This fixture uses revision `r0` and the local image ID as its digest. It stays in the runner's temporary directory and does not reserve a revision, create a GitHub release, or publish release tags.
  The GitHub release's `published_at` is the authoritative publication timestamp.
  Draft assets are not published versions.
- Prerelease versions create GitHub prereleases and never become GitHub's latest release.
  Tracks may also set `prerelease: true` when upstream uses numeric versions without a prerelease suffix, as Sonarr does.
  Such tracks must suffix their image version, for example with `"${version}-prerelease"`; neither the bare numeric version nor its unsuffixed revision is published automatically.
  In track mode only the owner of `latest` can become the latest release.

If publication fails, it may leave an untagged image and a draft release.
Keep the draft as a revision reservation and rerun the workflow, which allocates a new revision.
Do not delete release history or repurpose revision tags.
The workflow checks the registry before tagging.
If the revision already exists or the registry response cannot be verified, the run fails to prevent an overwrite.
GitHub releases and registry updates are not an atomic transaction: if an alias update fails, some aliases may already have moved.
A successful rerun repairs them.
Restrict other workflows and users from modifying these image tags.

### PR preview images

Every eligible same-repository PR publishes two tags per track.
For PR 12's stable track in `tuxcrate/zrepl`:

```text
ghcr.io/tuxcrate/zrepl-pr:pr-12-stable
ghcr.io/tuxcrate/zrepl-pr:pr-12-stable-<full-merge-commit-sha>
```

The first tag follows the PR.
The second identifies the exact merge commit tested by `pull_request`, not just the PR branch's head commit.
Rerunning the same commit may refresh OS packages and replace either tag; pin the image digest when an exact artifact is required.
Tracks have separate tags to avoid collisions.
The preview package always derives from the caller repository, regardless of any production `image` override in `meta.yaml`.

```sh
docker pull ghcr.io/tuxcrate/zrepl-pr:pr-12-stable
```

Preview builds retain uncached multiarch smoke tests, provenance, and SBOMs, but do not allocate release revisions, publish GitHub releases, move production aliases, or notify the website.
The shared cleanup workflow removes closed-PR previews when installed as described below.

After a successful push, the workflow posts pull commands, the tested merge commit, platforms, image digest, and a build link in the PR.
The same comment includes the generated `release.json` in a collapsed section labeled as synthetic validation metadata, with a note that its revision and digest are placeholders.
Subsequent builds update the same bot-authored comment for each track.
Fork PRs do not receive image comments because they do not publish images.

The caller must allow `packages: write` and `pull-requests: write`, as in the workflow example above.
Fork PRs do not log in or push.
Keep GitHub's default read-only token policy for fork PRs.
Never switch to `pull_request_target` to publish fork code.
Same-repository publishing uses `GITHUB_TOKEN` in the build job.
The `-pr` package has a separate name, but this does not restrict what the token can access.
Only trusted contributors should be able to create branches in the repository.

On first publication, set the new `-pr` package's visibility to public if anonymous pulls are intended.
For an existing preview package, grant the caller repository Actions write access, just as for the production package.

### Cleaning up PR previews

Add a separate `.github/workflows/container-pr-cleanup.yml` to each image repository:

{% raw %}
```yaml
name: Clean up container PR previews

on:
  pull_request:
    types: [closed]
  schedule:
    - cron: '41 3 * * *'
  workflow_dispatch:
    inputs:
      dry-run:
        description: Report matching images without deleting them
        default: true
        type: boolean

permissions:
  contents: read

jobs:
  cleanup:
    if: github.event_name != 'pull_request' || github.event.pull_request.head.repo.full_name == github.repository
    permissions:
      contents: read
      packages: write
      pull-requests: read
    uses: tuxcrate/github-actions/.github/workflows/container-pr-cleanup.yml@main
    with:
      dry-run: ${{ github.event_name == 'workflow_dispatch' && inputs.dry-run || false }}
```
{% endraw %}

Publish the shared workflow and tooling before enabling callers.
For a pinned caller, set `with.shared-ref` to the same ref as `uses`.
Install the caller on the default branch so closed-PR events and scheduled sweeps can run.

The close event covers both merged and unmerged same-repository PRs; fork close events are skipped because forks do not publish previews.
Every run checks current PR state through the API and scans all historical preview tracks and commits, including tracks no longer in `meta.yaml`.
The daily schedule catches older closed PRs, missed events, and previews left by late builds.
Manual runs default to dry-run mode; inspect their logs before disabling it to perform deletion.
No organization-wide token or additional secret is needed.

The caller repository's `GITHUB_TOKEN` needs **admin access to its `-pr` package** to delete versions, in addition to the workflow's `packages: write` permission.
Packages created by that repository's workflow normally grant this automatically; check the package's **Manage Actions access** settings for existing packages.
Production publishing access alone does not establish access to the separate preview package.
GitHub can report inaccessible packages as not found; a missing/inaccessible package is logged and skipped, so verify package access if previews remain.

Cleanup is limited to `ghcr.io/<caller repository>-pr`, even when production uses an overridden image name.
It deletes entire package versions, not merely tag names:

- All tags on a tagged version must identify closed PRs. Open-PR images and versions with unknown tags are retained.
- Eligible image roots are processed oldest first using their creation timestamp (with a version-ID tie-breaker). If no tagged version would otherwise remain, the newest eligible tagged image and its complete manifest graph are retained because GHCR rejects deletion of the last tagged version. Once a newer preview exists, a subsequent sweep can remove the older retained image. This does not delete or recreate the package, so its visibility and access settings remain intact.
- The registry's manifest graph identifies associated platform images and provenance/SBOM attestations. Descendants still referenced by retained images are preserved.
- New preview indexes carry repository and PR annotations, allowing cleanup to recognize untagged indexes left by reruns. Older untagged images without provable PR ownership are retained rather than guessed from timestamps.
- Discovery and PR-state checks must succeed before deletion. Cleanup rechecks closed PRs and the package snapshot before deleting; changed state aborts the run for a later retry.
- Children are deleted before their index so a partial failure leaves its ownership discoverable on a retry. Registry-managed blobs are not deleted individually.

The close-event cleanup shares the PR build's concurrency group, so it waits for that PR's active build.
Scheduled sweeps can overlap other PR builds; the snapshot check detects changes during discovery, and a later sweep catches previews published after a cleanup run.
Production packages, Git tags, GitHub releases, and the preview package itself are never deleted.
GitHub package deletion restrictions, such as public versions exceeding GitHub's download threshold, fail the run rather than bypassing protection.

Cleanup uses ordinary `pull_request: closed` events, not `pull_request_target`; no opt-out from GitHub's public-repository event policy is needed.
The caller and shared job both skip fork close events, keeping fork tokens read-only.
The workflow checks out trusted shared tooling, never caller or PR sources, and never builds or executes PR code.
Do not pass an untrusted PR ref as `shared-ref`.
The shared workflow temporarily also accepts existing same-repository `pull_request_target: closed` callers so the shared change can be published before migrating callers; replace that trigger with the example above to avoid GitHub's November 2, 2026 policy restriction.

### Required root metadata and release tracks

Keep application and base-image pins in the root `meta.yaml`.
A single stable track is enough; add preview or older maintained tracks only when needed.
For example:

```yaml
tracks:
  - name: stable
    version: "1.2.3"
    baseImage: debian:13-slim@sha256:a29215f6a35e51e22adffa17f89e9d2ef06214e64a2bad10d765c46aea49f11f
    tags: ["${version}", latest, stable, "${major}.${minor}"]

  - name: preview
    version: "2.0.0-rc.1"
    baseImage: debian:13-slim@sha256:a29215f6a35e51e22adffa17f89e9d2ef06214e64a2bad10d765c46aea49f11f
    tags: ["${version}", preview]
    buildArgs:
      PACKAGE_REVISION: "1"
```

To migrate existing callers, remove `app-version`, `tracks-file`, `image`, `context`, `containerfile`, `build-args`, and `platforms` inputs from callers.
Move any non-default build settings into `meta.yaml`: `image` at the top level and `context`, `containerfile`, `platforms`, and `buildArgs` on the relevant tracks.
Move application versions into tracks with explicit aliases, and move metadata from any other directory to the repository root.
These workflow inputs and the release planner's legacy environment-based configuration are no longer supported.

A complete example is in [`examples/meta.yaml`](https://github.com/tuxcrate/github-actions/blob/main/examples/meta.yaml).
Its versions are fictional.
Each Containerfile must be able to install the chosen version on every configured architecture.
Track configuration does not discover upstream releases or make unavailable prerelease packages available.

Configuration supports an optional top-level `image` and per-track `baseImage`, `context`, `containerfile`, `platforms` (comma-separated), `buildArgs` (string map), and `upstream` discovery metadata.
Application versions may use three or four numeric components (`X.Y.Z` or `X.Y.Z.W`), with an optional prerelease suffix.
Set `prerelease: true` on tracks whose upstream releases are prereleases despite having purely numeric versions.
This flag is carried through the build matrix to release reservation and cannot be used to make a suffixed prerelease stable.
An image-version suffix also implies prerelease behavior, even if the upstream version is numeric.
Such tracks may only own named aliases like `develop` or `preview`, never `latest`, `stable`, or numeric series aliases.

The planner skips tracks explicitly marked `prerelease: true` when any non-prerelease track has a higher application version, regardless of track names or order.
This applies to both PR builds and production releases.
Versions are compared numerically across all three or four components; a missing fourth component is treated as zero.
A stable version is also newer than a suffixed prerelease with the same numeric components.
For example, stable `6.4.4.10685` suppresses a prerelease track pinned to `6.4.4.10684`.
Tracks with a prerelease suffix but no explicit `prerelease: true` are not filtered.
Skipped tracks are still validated, including tag ownership; equal versions remain subject to the existing ownership checks.
Existing images, tags, and releases are left unchanged.

The APT and PyPI datasource restrictions below remain unchanged.
Supported datasources are:

- `deb`: Debian package `depName`, HTTP(S) `registryUrl` with `suite`, `components`, and `binaryArch` query parameters, and full stable `X.Y.Z-N` package `version`.
  The release tooling strips the package revision for image tags and releases, but passes the full package pin as the `APP_VERSION` build argument.
- `pypi`: PyPI package `depName` and stable `X.Y.Z` package `version`.
  An optional HTTP(S) `registryUrl` selects an alternate index; omit it for public PyPI.
  The package version becomes `APP_VERSION` unchanged.
  Other PEP 440 formats, including prereleases, post releases, epochs, and local versions, are not supported.
- Other Renovate datasource identifiers, including `github-releases`: a nonempty `depName`, a supported three- or four-part `version`, and an optional HTTP(S) `registryUrl`.
  Configure any tag-prefix extraction and versioning in Renovate; the Containerfile must install the exact version.

When using `upstream`, omit the track-level `version`.
All datasources inject the exact package or application pin as `APP_VERSION`.
Without `upstream`, the track's `version` is used unchanged.
Containerfiles use `ARG APP_VERSION` to receive the pin; there is no separate package-version build argument.
For example:

```yaml
tracks:
  - name: stable
    upstream:
      datasource: pypi
      depName: gallery-dl
      version: "1.32.16"
    baseImage: debian:13-slim@sha256:a29215f6a35e51e22adffa17f89e9d2ef06214e64a2bad10d765c46aea49f11f
    tags: ["${version}", "${major}", "${major}.${minor}", latest]
```

The release tooling never uses registry metadata to fetch or execute anything.
Renovate parses it as YAML for discovery, regardless of key order.
The Containerfile configures the package source and installs the pinned version.
`registryUrl` is used only for discovery and is not a build argument.
`baseImage` belongs to each track; a top-level `baseImage` is rejected.
The YAML decoder also rejects unknown fields, duplicate keys, and multiple documents.
Omitted build settings use the standard defaults above.
Additional build arguments are declared only in each track's `buildArgs`; `APP_VERSION` and `BASE_IMAGE` are reserved and cannot be overridden there.
`APP_VERSION` is always supplied by the release planner in the workflow's build arguments.
The `${version}` placeholder uses the application version without the Debian package revision.
`APP_VERSION` remains the exact installation pin and never receives a synthetic image suffix.
Image labels use the expanded image version, including any configured suffix.
All tracks share one image repository; tracks installing the same application version must use distinct image versions and tags.

### Explicit tags and immutable revisions

Every track must declare a nonempty `tags` list with exactly one template containing `${version}`.
This template must be `${version}` or `${version}-<suffix>`, and its expanded value must be a supported three- or four-part version with an optional prerelease suffix.
Its position in the list does not matter.
The planner expands `${major}` and `${minor}` too; quote templates in YAML.

For an upstream release that is numeric but not stable:

```yaml
tracks:
  - name: prerelease
    upstream:
      datasource: github-releases
      depName: Sonarr/Sonarr
      version: "5.0.0.2668"
    prerelease: true
    tags:
      - "${version}-prerelease"
      - "${major}-prerelease"
      - "${major}.${minor}-prerelease"
```

The installation pin is `5.0.0.2668`, while the image version is `5.0.0.2668-prerelease`.
The first publication creates immutable image tag `5.0.0.2668-prerelease-r0` and GitHub release tag `v5.0.0.2668-prerelease-r0`.
Configured tags `5.0.0.2668-prerelease`, `5-prerelease`, and `5.0-prerelease` follow its newest revision.
Neither `5.0.0.2668` nor `5.0.0.2668-r0` is generated.
Revision allocation is per image version, so stable and prerelease namespaces are independent.

`release.json` schema version 2 retains `version` as the application version and adds required `imageVersion` for the expanded image version.
`immutableTag` is `${imageVersion}-rN`; `aliasesAtPublication` records every configured expanded moving tag, including the version tag.
The website accepts both schemas: historical schema version 1 derives its image version from `version`.
Do not rewrite historical release assets during migration.

To migrate `meta.yaml`, rename `aliases` to `tags`, add `"${version}"` (or a suffixed equivalent), and replace `{major}` / `{minor}` with `${major}` / `${minor}`.
The old `aliases` field and placeholder syntax are rejected.
Deploy website schema support before publishing schema version 2 releases, and coordinate shared tooling and caller updates.
Old registry tags remain until explicitly retired; adding suffixed tags alone does not hide historical unsuffixed prerelease tags from Renovate.
If existing images are retagged into the new revision namespace, also reserve those revisions with matching Git tags at their original source commits so future releases cannot reuse them.

Rules:

- All tracks live on the default branch.
  PRs validate the complete configuration and build every track, publishing previews only when eligible.
  Releases build tracks one at a time under the existing repository-wide publishing lock.
  A failure in one track does not stop the others.
- Each track declares all moving tags explicitly in `tags`, including its `${version}` template.
  Only the immutable revision tag is created automatically.
- Tags may contain `${major}` and `${minor}`, e.g. `"${major}.${minor}"` becomes `0.8` for application version `0.8.0`.
  Expansion happens before validation and ownership checks, so duplicate or conflicting expanded aliases are rejected.
  Unknown placeholders are rejected.
  Prereleases still cannot own numeric series aliases.
  Removing a previously expanded series does not delete its old tag.
- Track names, image versions, and tags must be unique where applicable.
  No two tracks may own the same tag.
  Full versions other than the track's image version and revision-shaped tags cannot be declared as moving tags.
- Prereleases cannot own `latest`, `stable`, or numeric version-series aliases.
  Version build metadata (`+...`) is unsupported because `+` is not a Docker tag character.
  Versions ending in `-rN` are reserved for image revisions.
- Revisions are allocated per exact image version, including prerelease identifiers, using both Git tags and releases/drafts.
  They do not reset when a track is renamed or a version is reassigned to another track.
- Promotion requires a reviewed configuration change; build order does not promote tracks.
  Removing a track stops its builds but does not delete historical tags or remove its old moving aliases from GHCR.
  Retire obsolete aliases explicitly; retaining one must not be interpreted as a promise of maintenance.
- Keep alias ownership consistent across configuration changes.
  Do not repurpose a former exact-version alias for another application version.
  Use only one publishing caller/configuration per image repository.

PR builds are uncached on every configured platform so an earlier build cannot hide a missing APT package.
Make the container PR build check required in GitHub branch protection/rulesets.
Package discovery for one architecture is not proof of availability for another; rerun failed checks after delayed upstream publication.
PRs never publish production images or move production aliases.

Packaging changelogs are scoped to the previous release of the same track; pre-existing stable releases without a track marker remain compatible.

### Base-image configuration

Keep the full image name, readable tag, and multiarch manifest digest together:

```yaml
tracks:
  - name: stable
    version: "1.2.3"
    baseImage: debian:13-slim@sha256:a29215f6a35e51e22adffa17f89e9d2ef06214e64a2bad10d765c46aea49f11f
    tags: ["${version}", latest]
```

Each track declares its own `baseImage`; there is no top-level default.
Every configured reference must include the image name, tag, and SHA-256 digest; `13-slim@sha256:...` alone is not a full reference.
Verify the digest belongs to the selected tag and supports the target architectures.
Syntax validation cannot establish those registry facts.

Use this pattern in each applicable Containerfile:

```dockerfile
ARG BASE_IMAGE
FROM ${BASE_IMAGE}

ARG APP_VERSION
```

The planner passes the effective `BASE_IMAGE` argument to both PR and release builds, so the workflow does not duplicate the pin.
In track mode, set the pin with `baseImage`; setting `BASE_IMAGE` in track build arguments creates competing values that the planner rejects.
`baseImage` remains optional for compatibility with images that retain a literal `FROM` reference.
A parameterized Containerfile has no fallback: local builds must also supply `--build-arg BASE_IMAGE=...`.

The shared pipeline supplies `BUILDKIT_DOCKERFILE_CHECK=skip=InvalidDefaultArgInFrom` as a build argument in both PR and release builds.
This skips only the linter's requirement for a default `FROM` argument; all other checks remain enabled, and an absent or invalid `BASE_IMAGE` still fails the actual build.
No `# check=` directive or `ARG` declaration for this BuildKit option is needed in individual Containerfiles.
For the same behavior locally, pass `--build-arg BUILDKIT_DOCKERFILE_CHECK=skip=InvalidDefaultArgInFrom`.

The shared Renovate preset detects track `baseImage` fields in `meta.yaml`, using Docker versioning to retain suffixes such as `-slim`.
Tag and digest updates require review and trigger normal PR builds.
Publish the preset and shared tooling before migrating caller repositories.

### Website integration

The website can read `release.json` assets from public GitHub releases and resolve all current tags directly against GHCR.
Historical alias lists record assignments at publication time.
They do not show current assignments.
Releases created before this metadata was added remain valid; the website lists them without adding data it does not have.

For immediate refreshes, optionally add this to the caller job:

{% raw %}
```yaml
with:
  docs-repository: tuxcrate/docs
secrets:
  docs-token: ${{ secrets.DOCS_TOKEN }}
```
{% endraw %}

Use a GitHub App installation token or fine-grained token with contents: write on the docs repository only.
The caller's `DOCS_TOKEN` repository secret is passed as `docs-token`.
The caller's `GITHUB_TOKEN` cannot dispatch to a different repository.
Never pass the website token into builds or PR jobs.
One notification is sent after all release tracks finish successfully; PR builds and failed releases do not notify.
A missing token produces a warning.
If the notification fails, the release still succeeds; the website refreshes on its hourly schedule.
Configure `DOCS_TOKEN` as a repository secret, or an organization secret available to each caller.
Without this optional token, the website still refreshes on its schedule or a manual run.

### Setup

1. Publish this repository's workflow and tooling before enabling a caller.
2. Allow the caller to use the shared workflow under the organization's Actions policy and allow `contents: write` and `packages: write` for releases.
3. For an existing GHCR package, grant the caller repository Actions write access.
   Set package visibility to public if anonymous pulls are intended; publishing with `GITHUB_TOKEN` does not itself guarantee public visibility.
4. Ensure repository tag rules allow `GITHUB_TOKEN` to create the `vX.Y.Z-rN` release tags (and prerelease equivalents when used).

Rebuilding refreshes installed packages.
To update a digest-pinned base image, merge its digest update.
Neither action fixes vulnerabilities compiled into an upstream binary.
Those may require a new upstream release or an application rebuild with a newer toolchain.
A scheduled rebuild does not necessarily fix a vulnerability.

## Development

```sh
go test -race ./...
go vet ./...
actionlint
```

The release CLI lives in `cmd/container-release`.
The preview cleanup CLI lives in `cmd/container-pr-cleanup`; use `-dry-run` with `GITHUB_REPOSITORY` and `GH_TOKEN` set to inspect candidates without deleting anything.
It is written in Go and uses `go.yaml.in/yaml/v3` for strict YAML parsing.
The workflow compiles it using the Go toolchain provided by the Ubuntu runner; Go 1.23 or newer is required.
Build it with `go build -o /path/to/container-release ./cmd/container-release`.
Run the binary from the container source checkout with `plan`, `metadata`, `manifest`, or `reserve` and the required workflow environment variables set.
Publication commands receive `APP_VERSION` (the application version, without an APT package revision), `IMAGE_VERSION` (the expanded version tag), and `TAGS` (a JSON array of expanded moving tags) from the planner's build matrix.
Only the Containerfile's build argument receives a full APT package pin.
The `plan` command always reads `meta.yaml` from the current directory; it has no alternate path or environment fallback.
The `reserve` command creates a real draft release; use `go test` for validation without publishing.

Changelog integration tests use Git directly.
CI runs all tests on every PR and default-branch push.
Third-party actions are pinned to commit SHAs and updated through the shared [Renovate preset](https://github.com/tuxcrate/renovate-config).
The repository's `renovate.json` extends that preset; install and enable the Renovate GitHub App to activate updates.
