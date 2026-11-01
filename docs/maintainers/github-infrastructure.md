# GitHub infrastructure

The `infrastructure/` directory in [`tuxcrate/.github`](https://github.com/tuxcrate/.github)
contains OpenTofu configuration for repository metadata and branch protection.
Run OpenTofu from that directory, with a current sibling `docs/` repository
checkout in the workspace. Container repository descriptions and topics come
from the [image-page front matter](website.md#image-pages).

## Local validation

OpenTofu encrypts state and plans. Provide `state_passphrase` securely and
keep it out of Git. GitHub authentication comes from `GITHUB_TOKEN`.

Validate without applying changes:

```sh
tofu init -backend=false -lockfile=readonly
tofu fmt -check -recursive
tofu validate
```

The infrastructure Actions workflow checks formatting only; it does not plan
or apply organization changes. Review a plan before applying changes.

## Importing existing repositories

Before adopting an existing repository, import its repository, default branch,
and existing branch protection into the corresponding module resources.
Check `tofu state list` first and import only resources that are not already
managed in state. Existing repositories must not be created or replaced.

For example, to adopt `renovate-config` if none of its resources are in state:

```sh
tofu import 'module.repository["renovate-config"].github_repository.this' renovate-config
tofu import 'module.repository["renovate-config"].github_branch_default.this' renovate-config
tofu import 'module.repository["renovate-config"].github_branch_protection_v3.this' renovate-config:main
```

These imports update local state, not GitHub settings.

## Required container checks

Container repositories require `container / pull-request-check`, which covers
planning and every active track build. See the
[container release guide](container-releases.md#explicit-tags-and-immutable-revisions)
for validation requirements and the rollout order when migrating from
per-track required checks.
