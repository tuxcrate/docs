# Website development

The Tuxcrate website is built with Zensical.
Its source lives in [`tuxcrate/docs`](https://github.com/tuxcrate/docs).
Run the commands below from the root of that repository.

## Image pages

Container pages use a shared Markdown/Jinja template at `templates/container.md.jinja`.
Add `docs/containers/<name>.md` with YAML front matter and extend the template:

{% raw %}
```markdown
---
title: example
container:
  repository: tuxcrate/example
  topics: [containers, docker, example]
  upstream: https://github.com/example/example
  description: A short description of the tool.
  docker_run:
    - --rm
    - '--publish 8080:8080'
    - ghcr.io/tuxcrate/example:latest
  compose:
    services:
      example:
        image: ghcr.io/tuxcrate/example:latest
        ports:
          - "8080:8080"
---

{% extends "container.md.jinja" %}

{% block prerequisites %}
Requirements and setup steps that must be read before running the examples.
{% endblock %}

{% block details %}
## Configuration

Tool-specific configuration and usage notes.
{% endblock %}

{% block tags %}
## Choosing a tag

Explain the tags supported by this image.
{% endblock %}
```
{% endraw %}

The template supplies the title, Upstream / Container source / GHCR buttons,
description in an info admonition, CLI and Compose tabs with line numbers, and a version table.
Next to the GHCR button, a pulls badge links to the same package page and shows
GitHub's total package downloads (not unique users).
The browser loads this badge from the third-party
[ghcr-badge service](https://github.com/eliasbenb/ghcr-badge); its count may be cached.
It is not fetched during builds, so service outages do not block deployment or
offline builds, though viewing the badge requires network access.
Keep `container.description` to two or three sentences explaining what the tool does.
Put configuration details and prerequisites in the corresponding Markdown blocks.
All three content blocks are optional; use them to keep longer documentation in Markdown.
Navigation discovers pages in `docs/containers/` automatically.

The OpenTofu configuration in the `infrastructure/` directory of `tuxcrate/.github`
also reads this front matter for GitHub repository About settings.
`container.description` supplies the description and `container.topics` supplies
the GitHub topics. Do not list `tuxcrate`: OpenTofu adds it automatically.
Topics are lowercase names using
letters, numbers, and hyphens (at most 20 topics, each at most 50 characters).
The homepage is derived as `https://tuxcrate.com/containers/<name>/` from the page
filename, which must match the repository name. Descriptions must fit GitHub's
350-character limit. Publishing a docs change does not itself update GitHub:
an infrastructure maintainer must review/apply a plan using the updated docs checkout.
New containers must be added to `infrastructure/repositories.tf` in `tuxcrate/.github`.
Container repositories require the shared workflow's fixed
`container / pull-request-check` aggregate check, which covers planning and all
active tracks without requiring checks for dormant prereleases.

`docker_run` is a nonempty list of single-line shell fragments, one per output line.
Do not include `docker run` itself. Keep shell quoting explicit: fragments are joined,
not shell-escaped, so `$PWD` and `$(id -u)` continue to expand when users run the command.
Include any directory creation or environment setup in the `prerequisites` block.

`compose` is a native YAML mapping containing `services`. The macro serializes it
with key order preserved. Quote values that must remain strings, such as `"no"`
or port mappings. Author the two examples independently; they are not converted
into each other.

Published container images must be public at `ghcr.io/<owner>/<name>`.
Every container page fetches version data automatically.

The template calls `gh_image_versions_data(container.repository)` for structured data:
the image name, verified releases with their current tags, and a preview flag.
Python handles fetching, validation, and ordering of verified releases.
The template owns the table, tag buttons, notices, links, and default tag used by
the initial CLI and Compose examples, without requiring JavaScript.
JavaScript enables changing the selected tag after the page loads.
It also limits the table to the three newest releases initially; “List more” reveals
five more at a time, keeping the button visible while more remain.
Without JavaScript, all releases remain visible.
Each non-stable track shows a warning when its highest verified application
version is lower than stable's highest verified version. Comparisons use numeric
version components, ignore image revisions and publication dates, and rank a
stable version above its prerelease suffix. Equal or newer tracks show no warning.
If the release representing that highest version is marked as a prerelease in
GitHub, the warning also says that its image will no longer receive
security updates. This uses the GitHub release's `prerelease` flag, not the track
name or version suffix; `release.json` does not currently contain that flag.
The data macro accepts short names resolving to `tuxcrate/<name>` as well as `owner/name`.

Zensical's built-in macros plugin loads `macros/main.py` and renders the table during `build` or `serve`.
You do not need a separate generator, Go toolchain, Python requirements file, or third-party plugin installation.

### Sources of truth

- GitHub releases and their `release.json` assets provide application versions, image revisions, tracks, platforms, and immutable release history.
  Schema version 2 includes `imageVersion` for suffixed image tags while `version` remains the upstream application version.
  The website accepts both schema versions 1 and 2 and continues comparing application versions, not synthetic image suffixes.
  Drafts are excluded; prereleases are included.
  The table lists verified releases newest first, with their revision tags, application versions, and publication dates.
  Revision tags link to GitHub releases, with a GHCR link beside each tag.
  Links below the table provide access to all releases and registry tags, including older releases without metadata.
- GHCR's tag list and current manifest digests verify that each displayed revision tag still matches its release metadata.
  The plugin fetches all pages of both APIs; missing or mismatched revision tags are excluded.
  Tags without matching metadata are not displayed; the plugin does not infer versions from tag names.
- Repositories without published `release.json` metadata show “No releases available yet”.
  They do not query GHCR, which may not have a package before the first release.
  An empty registry tag list also shows this message. API errors still stop the build.
- Each build takes a snapshot of the data.
  Tags can move during a build; the next build picks up those changes.
  The plugin never modifies registry tags or release history.
- `GH_TOKEN` (or `GITHUB_TOKEN`) authenticates GitHub API calls when supplied.
  The plugin does not send the token when downloading public release assets, and GHCR uses anonymous pulls.
  An API or rendering failure stops the build, so partial tables are never deployed.

## Local development

Install [Task](https://taskfile.dev/), then start the local preview:

```sh
task
```

Open <http://localhost:8000>.
The task uses Docker and reads the Zensical image from `.github/workflows/docs.yml` so the preview stays in sync with CI.
It uses offline fixtures for image versions, labeled as fictional test data, so no GitHub or registry access is needed.
If set, `GH_TOKEN` and `GITHUB_TOKEN` are passed through to the container.

For a preview with live release and registry data:

```sh
GH_TOKEN="$(gh auth token)" task live
```

This performs a clean build before serving so cached offline fixtures are not reused.
The token command requires an authenticated GitHub CLI; you can also supply an existing
`GH_TOKEN` or `GITHUB_TOKEN` environment variable.

To build:

```sh
docker run --rm -v "$PWD:/docs" zensical/zensical:0.0.71 build --clean --strict
```

For an offline build with fictional data labeled as such:

```sh
docker run --rm -v "$PWD:/docs" \
  -e GH_IMAGE_VERSIONS_FIXTURE=macros/tests/fixtures/images.json \
  zensical/zensical:0.0.71 build --clean --strict
```

`--clean` forces macros to refresh even when Markdown is unchanged, and prevents cached preview data from being reused in a live build.

Run the same checks as CI with Python 3.13 and Node.js 22.
Install the test dependencies in a virtual environment:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-test.txt
```

Then run the linter, Python macro and template tests, and JavaScript pagination tests.
The tests themselves need no network access:

```sh
ruff check .
python -m pytest macros/tests
node --test macros/tests/test_container_tags.cjs
```

## Publishing

The website workflow runs Ruff, pytest, and the Node.js tests before building or deploying.
PR builds use live GitHub release and GHCR data, just like deployment builds.
All build events use the job's read-only `GITHUB_TOKEN` for GitHub API calls;
GHCR checks remain anonymous so CI verifies that documented images are public.
Unreleased container pages can pass with an empty version table. Once release
metadata exists, the build verifies the public registry package. Offline fixtures
remain available for tests and local preview, but are not used by CI's website build.
Default-branch pushes, manual runs, hourly schedules, and `image-published` repository dispatches build with live data and deploy GitHub Pages.
Builds use `docker://zensical/zensical:0.0.71` directly as a GitHub Actions step.
Only the test job installs Python dependencies; the build needs no explicit `docker run` command.

Before enabling deployment:

1. Publish the shared `tuxcrate/github-actions` tooling so image releases include `release.json` metadata.
2. Confirm each GHCR package exists and is public.
   A `403` from `ghcr.io/token` usually means it has not been published or anonymous pulls are disabled.
3. Select GitHub Actions as the Pages source and allow the `github-pages` environment to deploy from `main`.
4. Set `site_url` in `zensical.toml` once the canonical domain is chosen.
5. Optionally configure `docs-repository` and `docs-token` in image callers for immediate refreshes.
   The callers map the `DOCS_TOKEN` repository secret to `docs-token`.
   The hourly refresh needs no cross-repository secret.

If fetching data or building fails, the last successful deployment stays online.
