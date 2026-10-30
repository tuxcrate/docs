# Container runtime tests

Container repositories can provide `tests/smoke.sh` to test their final images
without shipping test scripts, fixtures, databases, or startup side effects in
image layers. The shared container workflow runs the script on the Linux CI
runner, not inside the image build.

## Build, test, then publish

For every active track, both PR and production jobs follow this order:

1. Build every configured platform without layer cache and export one local OCI
   archive. BuildKit records provenance and SBOM attestations in that archive.
   This step does not push an image to a registry.
2. Load each requested platform from the archive into the local Docker daemon
   using Skopeo. Verify the archive contains exactly one matching platform image
   and that the loaded image has the expected OS and architecture.
3. Run `tests/smoke.sh` once for each platform, when the hook exists. QEMU enables
   execution of non-native platforms on the GitHub runner. A failing hook fails
   the track; there is no automatic retry of the entire test.
4. Validate release metadata, including OS identification from the first tested
   platform image, before any upload.
5. Log in to GHCR and copy the original archive by digest with
   `skopeo copy --all --preserve-digests`. This preserves the multiarchitecture
   index, platform manifests, annotations, provenance, and SBOMs. There is no
   rebuild between testing and publication.
6. Publish PR preview tags or continue production revision reservation, image
   tagging, and GitHub release publication.

An unsuccessful build or test never uploads image manifests or layers to GHCR.
BuildKit's GitHub Actions cache may still be written; it is not a published
container image. A later publication failure can leave an untagged registry
artifact or draft release, as described in [Container releases](container-releases.md).
The ordering applies per track: one failing track does not prevent another
independent track from completing.

Fork PRs use the same local build and test path but never log in or upload.
Do not use `pull_request_target` to run these tests or publish PR code.

The shared helper records a successful test receipt next to the archive and
checks its checksum before uploading. Missing receipts or modified archives
fail publication. This is an accidental-misuse guard, not a security boundary
against malicious code already executing on the runner.

## Hook interface

Create a regular file at the **repository root's** `tests/smoke.sh`, regardless
of a track's build context. It does not need an executable bit: the runner calls
it with Bash from the repository root:

```sh
bash tests/smoke.sh IMAGE APP_VERSION PLATFORM
```

| Argument | Meaning |
| --- | --- |
| `IMAGE` | Unique local Docker image reference loaded from the built archive; use it without pulling or rebuilding |
| `APP_VERSION` | Exact installation pin from the track, including an APT package revision when applicable |
| `PLATFORM` | Requested platform, such as `linux/amd64` or `linux/arm64` |

The same script handles all tracks. Use the expected version argument instead
of hard-coding a release. Helpers and fixtures may live elsewhere under `tests/`;
the pipeline does not automatically execute every file in that directory.

The runner supplies `TUXCRATE_TEST_ID`. Label every test container with
`io.tuxcrate.smoke-test=$TUXCRATE_TEST_ID` so the shared helper can remove it if
the hook times out or is interrupted. Each invocation has a five-minute timeout,
followed by a 30-second termination grace period. Hooks should use shorter
readiness and shutdown limits and their own cleanup traps.

Repositories without a hook keep their existing Containerfile assertions and
receive platform and OS-metadata validation, but **do not receive an
application-specific runtime smoke test**. This compatibility behavior allows
repositories to migrate individually; CI prints the missing-hook notice.

## Writing a test

Run the production entrypoint as the image's configured user. Do not override
it merely to make startup pass. Check readiness through an application endpoint
where available, check the installed version, and confirm graceful shutdown.
Check runtime ownership, writable configuration directories, licenses, and
required tools as appropriate for the application.

Use disposable container writable layers or volumes for generated data. Do not
mount the source checkout over application directories, use production data,
install test packages into the image, or commit a tested container back into an
image. Prefer no host port mappings; `docker exec` can query a loopback endpoint
inside the container. The Sonarr, Radarr, and Prowlarr hooks run with
`--network none`, since their smoke tests require no external services.

A minimal host-side hook looks like this:

```bash
#!/usr/bin/env bash
set -euo pipefail

image=${1:?Image required}
version=${2:?Version required}
platform=${3:?Platform required}
container=
cleanup() {
    status=$?
    if [[ -n $container ]]; then
        if ((status != 0)); then
            docker logs "$container" >&2 || true
        fi
        docker rm --force --volumes "$container" >/dev/null || true
    fi
    exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

container=$(docker create --pull=never --platform "$platform" \
    --label "io.tuxcrate.smoke-test=${TUXCRATE_TEST_ID:-manual-$$}" "$image")
docker start "$container" >/dev/null

# Add bounded, application-specific readiness and exact-version checks here.
# Use "$version"; do not treat successful docker start as application readiness.

docker stop --time 30 "$container" >/dev/null
test "$(docker wait "$container")" = 0
```

This skeleton is not a complete smoke test until readiness and version checks
are implemented. The three application repositories contain working examples.
On failure, print the failed check, container state, logs, and relevant file
listings before removing the container. Keep failures meaningful: retry transient
readiness conditions, not version mismatches or failed assertions after startup.

Hooks run host-side with Docker access and have the same contributor trust
requirements as Containerfiles. The helper unsets `GH_TOKEN` and `GITHUB_TOKEN`
for the hook, and the workflow does not log in to GHCR until testing finishes.
Never forward CI credentials or mount the Docker socket into an application
container. Same-repository build steps can still receive the existing optional
GitHub API BuildKit secret; fork builds cannot.

## Local validation

For a quick single-platform test, build and load the final image, then invoke
the hook from its repository. Substitute the track's real pins from `meta.yaml`:

```sh
docker buildx build --pull --no-cache --platform linux/amd64 --load \
  --build-arg APP_VERSION="$APP_VERSION" \
  --build-arg BASE_IMAGE="$BASE_IMAGE" \
  --build-arg BUILDKIT_DOCKERFILE_CHECK=skip=InvalidDefaultArgInFrom \
  --file Containerfile --tag tuxcrate-local:test .
bash tests/smoke.sh tuxcrate-local:test "$APP_VERSION" linux/amd64
```

To reproduce the shared artifact path on Linux, install Go, Bash, Docker/Buildx,
Skopeo, and QEMU/binfmt support for non-native execution. Build the shared Go
command once (from the `github-actions` checkout):

```sh
go build -o /path/to/container-artifact ./cmd/container-artifact
```

Then run the following from the image repository. Use a Buildx
builder that supports the OCI exporter, such as the `docker-container` driver:

```sh
docker buildx build --pull --no-cache --platform linux/amd64,linux/arm64 \
  --provenance=mode=max --sbom=true \
  --build-arg APP_VERSION="$APP_VERSION" \
  --build-arg BASE_IMAGE="$BASE_IMAGE" \
  --build-arg BUILDKIT_DOCKERFILE_CHECK=skip=InvalidDefaultArgInFrom \
  --file Containerfile --output type=oci,dest=/path/to/image.tar .
/path/to/container-artifact test \
  /path/to/image.tar linux/amd64,linux/arm64 "$APP_VERSION"
```

These commands do not publish anything. The helper retains the first loaded
image for OS-metadata validation and removes the other temporary image tags.
The first image tag is available as `image` in `GITHUB_OUTPUT` when that variable
is set; remove it with `docker image rm` when local validation is finished.
Remove the archive and its `.tested` receipt when they are no longer needed.

## Migrating an image repository

Publish the shared workflow and helper changes **before** migrating callers.
For pinned workflows, keep `uses` and `with.shared-ref` on the same published
ref. Do not disable existing startup tests until the shared hook is available.

Convert the old build-time test to a host-side Docker test. Remove the
Containerfile's smoke-test `COPY` and `RUN` instructions, and remove any
test-only dependencies or fixtures from the final image. Keep meaningful
installation assertions where useful. No new workflow inputs or `meta.yaml`
fields are needed. Require successful PR validation on both configured
architectures before merging the migration.
