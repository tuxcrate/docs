# Dependency updates

[`tuxcrate/renovate-config`](https://github.com/tuxcrate/renovate-config) contains the shared [Renovate](https://docs.renovatebot.com/) presets.
To use them, enable the Renovate GitHub App for each repository and add a `renovate.json` in its root.

## General repositories

```json
{
  "$schema": "https://docs.renovatebot.com/renovate-schema.json",
  "extends": ["github>tuxcrate/renovate-config"]
}
```

The default preset extends Renovate's recommended configuration, removes its PR rate limit, pins GitHub Actions to commit digests, and disables automerge.
Updates require review.

## Container image repositories

```json
{
  "$schema": "https://docs.renovatebot.com/renovate-schema.json",
  "extends": ["github>tuxcrate/renovate-config:images"]
}
```

The image preset includes the default policy.
It also:

- Pins Docker image dependencies to digests.
- Updates each track's complete `baseImage: image:tag@sha256:...` reference in `meta.yaml`, retaining Docker tag suffixes such as `-slim`.
- Uses one JSONata manager to read each track's `upstream.datasource`, `depName`, `version`, and optional `registryUrl` directly from YAML.
  The datasource is selected dynamically within that manager.
- Applies datasource-specific version rules: `deb` uses Debian versioning and stable `X.Y.Z-N` pins; `pypi` uses PEP 440 versioning and stable `X.Y.Z` pins.
  Omit `registryUrl` to use public PyPI.
- Keeps the shared `tuxcrate/github-actions` workflow on its coordinated tooling ref without pinning it independently to a digest.
  If pinning the workflow manually, keep its `uses` ref and `shared-ref` input identical.

APT discovery checks only the configured architecture.
For zrepl this is `amd64`.
Require successful uncached `linux/amd64` and `linux/arm64` PR builds before merging; rerun a failed build if upstream publishes the second architecture later.
Discovery does not confirm that the package is available for both architectures.

The Renovate extractor can discover other datasources too.
The shared release planner, however, currently accepts only `deb` and `pypi` upstream metadata.
Additional sources need compatible planner validation, version rules, and Containerfile installation logic.
Custom JSONata dependencies otherwise default to `semver-coerced` versioning unless a package rule overrides it.

See [container releases](container-releases.md) for the metadata schema.
Publish shared tooling and preset changes before migrating image repositories.
