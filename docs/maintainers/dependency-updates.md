# Dependency updates

[`tuxcrate/renovate-config`](https://github.com/tuxcrate/renovate-config) contains the shared [Renovate](https://docs.renovatebot.com/) presets.
To use them, enable the Renovate GitHub App for each repository and add a `renovate.json` in its root.

## Using Tuxcrate images

If your repository uses Tuxcrate images, add the standalone `tuxcrate` preset to your existing Renovate configuration:

```json
{
  "$schema": "https://docs.renovatebot.com/renovate-schema.json",
  "extends": ["github>tuxcrate/renovate-config:tuxcrate"]
}
```

It supports `X.Y.Z-rN` and `X.Y.Z.W-rN` image tags from `ghcr.io/tuxcrate/**`, including numeric revision updates such as `-r9` to `-r10`.
Image revision changes are patch updates.
Floating aliases and prerelease tags are excluded.
Numeric upstream prereleases must use suffixed image tags such as `5.0.0.2668-prerelease-r0`; tags such as `5.0.0.2668-r0` look like stable releases.
Image repositories configure this with `tags: ["${version}-prerelease", ...]`; the upstream pin stays numeric.
Historical unsuffixed prerelease tags must be retired separately or consumers can still discover them.

This preset only configures versioning.
It does not inherit Tuxcrate's repository policies or change your automerge, digest pinning, or scheduling settings.
Publish the preset before adding the import to consuming repositories.

## General repositories

```json
{
  "$schema": "https://docs.renovatebot.com/renovate-schema.json",
  "extends": ["github>tuxcrate/renovate-config"]
}
```

The default preset extends Renovate's recommended configuration, removes its PR rate limit, pins GitHub Actions to commit digests, and enables semantic commits.

Automerge is disabled by default, with package rules enabling GitHub's native PR automerge for minor, patch, pin, pin-digest, digest, and lock-file maintenance updates.
Major updates remain subject to review and are assigned to `Skaronator`.
Configure branch protection or rulesets with required checks so automerge cannot bypass validation.
For container repositories, require successful uncached builds on both supported architectures.

## Container image repositories

```json
{
  "$schema": "https://docs.renovatebot.com/renovate-schema.json",
  "extends": ["github>tuxcrate/renovate-config:images"]
}
```

The image preset includes the default policy and adds these rules:

- Pins Docker image dependencies to digests.
- Updates each track's complete `baseImage: image:tag@sha256:...` reference in `meta.yaml`, retaining Docker tag suffixes such as `-slim`.
- Uses one JSONata manager to read each track's `upstream.datasource`, `depName`, `version`, and optional `registryUrl` directly from YAML.
  The datasource is selected dynamically within that manager.
  The track name becomes Renovate's `depType`, so repositories can apply different `matchDepTypes` policies to stable and prerelease tracks of the same upstream.
- Applies datasource-specific version rules: `deb` uses Debian versioning and stable `X.Y.Z-N` pins; `pypi` uses PEP 440 versioning and stable `X.Y.Z` pins.
  Omit `registryUrl` to use public PyPI.
- Keeps the shared `tuxcrate/github-actions` workflow on its coordinated tooling ref without pinning it independently to a digest.
  If pinning the workflow manually, keep its `uses` ref and `shared-ref` input identical.

APT discovery checks only the configured architecture, which is `amd64` for zrepl.
It does not confirm that the package is available for both architectures, so require successful uncached `linux/amd64` and `linux/arm64` PR builds before merging.
Rerun a failed build if upstream publishes the second architecture later.

The Renovate extractor also supports other datasources.
The shared release planner accepts other datasource identifiers with a nonempty dependency name and a supported three- or four-part application version.
Additional sources still need compatible version rules and Containerfile installation logic.
Custom JSONata dependencies otherwise default to `semver-coerced` versioning unless a package rule overrides it.
Sonarr uses `github-releases`, strips the leading `v` from release tags, and uses `loose` versioning for its four-part versions.
Its stable track ignores upstream prereleases; the develop track opts into them without following GitHub's latest stable release.
Image builds verify the upstream release's prerelease flag and branch-specific assets, rejecting a release from the wrong channel.

See [container releases](container-releases.md) for the metadata schema.
Publish shared tooling and preset changes before migrating image repositories.

### GitHub prerelease-only discovery

The `images` preset provides `custom.github-prereleases` for any public GitHub repository.
It reads the 100 most recent releases and includes only releases with `draft: false` and `prerelease: true`.
Stable releases are excluded even when their version is newer.
Release timestamps, changelog links, and the source repository URL are retained.

Opt in for the desired track in the image repository's `renovate.json`:

```json
{
  "extends": ["github>tuxcrate/renovate-config:images"],
  "packageRules": [
    {
      "matchDatasources": ["github-releases"],
      "matchDepTypes": ["prerelease"],
      "overrideDatasource": "custom.github-prereleases",
      "ignoreUnstable": false,
      "respectLatest": false
    }
  ]
}
```

Keep `upstream.datasource: github-releases` and `upstream.depName: owner/repo` in `meta.yaml`.
Set `matchDepTypes` to the actual track name, such as `develop`, and keep application-specific `extractVersion` and `versioning` rules locally.
The shared preset does not automatically change any track's release channel.
Builds must still verify the upstream channel and required architecture assets.

Publish this preset before removing repository-local datasource definitions.
