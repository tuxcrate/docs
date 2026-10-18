"""Exercise container metadata, rendering, and network safeguards."""

# These tests intentionally use unittest assertions and subtests together.
# ruff: noqa: PT009, PT027

import copy
import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.request import Request

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined

from macros import main

FIXTURE = Path(__file__).parent / "fixtures/images.json"
SNAPSHOT = json.loads(FIXTURE.read_text())
# Keep focused unit tests independent of the larger pagination preview fixture.
REPOSITORY = "tuxcrate/zrepl"
IMAGE = next(item for item in SNAPSHOT["images"] if item["repository"] == REPOSITORY)
IMAGE = {**IMAGE, "releases": IMAGE["releases"][:2]}


def template_environment() -> Environment:
    """Create the Markdown template environment used by the website."""
    root = Path(__file__).resolve().parents[2]
    # Markdown templates escape their individual table values, not the whole page.
    env = Environment(
        loader=FileSystemLoader(root / "templates"),
        undefined=StrictUndefined,
        autoescape=False,  # noqa: S701 -- Markdown values are escaped individually.
    )
    env.filters.update(
        cell=main.cell, docker_run=main.docker_run, compose_yaml=main.compose_yaml
    )
    env.globals["gh_image_versions_data"] = main.gh_image_versions_data
    return env


def render_versions(item: main.Metadata) -> str:
    """Exercise the real template with a controlled registry snapshot."""
    env = template_environment()
    container = {
        "repository": item["repository"],
        "upstream": "https://example.com",
        "description": "Test image",
        "docker_run": [item["image"] + ":latest"],
        "compose": {"services": {"app": {"image": item["image"] + ":latest"}}},
    }
    with (
        patch.dict(os.environ, {"GH_IMAGE_VERSIONS_FIXTURE": ""}),
        patch("macros.main.collect", return_value=item),
    ):
        return env.get_template("container.md.jinja").render(
            page={"meta": {"title": "Test image", "container": container}}
        )


class MacroTests(unittest.TestCase):
    """Check macro registration, version selection, and escaping."""

    def test_registration(self) -> None:
        """Register the macros and all three rendering filters."""
        env = Mock()
        main.define_env(env)
        self.assertEqual(
            env.macro.call_args_list,
            [
                unittest.mock.call(main.gh_image_versions_data),
                unittest.mock.call(main.container_pages),
            ],
        )
        self.assertEqual(
            env.filter.call_args_list,
            [
                unittest.mock.call(main.cell),
                unittest.mock.call(main.docker_run),
                unittest.mock.call(main.compose_yaml),
            ],
        )

    def test_container_pages_discovery(self) -> None:
        """Discover nested image pages, sort titles, and ignore other Markdown."""
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "index.md").write_text("# Container images\n")
            (root / "notes.md").write_text("---\ntitle: Notes\n---\n")
            (root / "nested").mkdir()
            for filename, title in (("z.md", "Zulu"), ("nested/a b.md", "alpha")):
                (root / filename).write_text(
                    yaml.safe_dump(
                        {
                            "title": title,
                            "container": {"description": f"About {title}"},
                        },
                        explicit_start=True,
                    )
                    + "---\n"
                )
            with patch("macros.main.CONTAINERS_DIR", root):
                images = main.container_pages()
        self.assertEqual(
            images,
            [
                {
                    "title": "alpha",
                    "description": "About alpha",
                    "url": "nested/a%20b.md",
                },
                {"title": "Zulu", "description": "About Zulu", "url": "z.md"},
            ],
        )

    def test_container_index(self) -> None:
        """Render the real index using image metadata without network requests."""
        env = template_environment()
        env.globals["container_pages"] = main.container_pages
        index = main.CONTAINERS_DIR / "index.md"
        with patch("macros.main.request", side_effect=AssertionError("Network used")):
            rendered = env.from_string(index.read_text()).render()
        self.assertIn("| [gallery-dl](gallery-dl.md) | gallery-dl is", rendered)
        self.assertIn("| [zrepl](zrepl.md) | zrepl is", rendered)
        self.assertNotIn("{{", rendered)

    @patch.dict(os.environ, {"GH_IMAGE_VERSIONS_FIXTURE": str(FIXTURE)})
    @patch(
        "macros.main.request",
        side_effect=AssertionError("Offline preview used the network"),
    )
    def test_offline_preview_and_short_name(self, request: Mock) -> None:
        """Resolve short names using fixtures without making network requests."""
        data = main.gh_image_versions_data("zrepl")
        self.assertEqual(data, main.gh_image_versions_data(REPOSITORY))
        self.assertTrue(data["preview"])
        self.assertEqual(data["image"], IMAGE["image"])
        self.assertEqual(
            [release["track"] for release in data["releases"][:2]],
            ["preview", "stable"],
        )
        self.assertNotIn("markdown", data)
        request.assert_not_called()

    def test_invalid_repository(self) -> None:
        """Reject malformed repository names before fetching data."""
        for name in (
            "../secret",
            "owner/name/extra",
            "https://example.com/repo",
            "Zrepl",
            "",
        ):
            with self.subTest(name=name), self.assertRaises(ValueError):
                main.gh_image_versions_data(name)

    @patch.dict(os.environ, {"GH_IMAGE_VERSIONS_FIXTURE": ""})
    @patch("macros.main.collect")
    def test_default_tag_prefers_verified_stable_release(self, collect: Mock) -> None:
        """Prefer stable, then a verified prerelease, then latest."""
        item = copy.deepcopy(IMAGE)
        for expected in ("1.2.3-r1", "2.0.0-rc.1-r0", "latest"):
            with self.subTest(expected=expected):
                collect.reset_mock()
                collect.return_value = item
                versions = main.gh_image_versions_data(REPOSITORY)
                collect.assert_called_once_with(REPOSITORY)
                if expected != "latest":
                    self.assertIn(
                        expected,
                        [release["immutableTag"] for release in versions["releases"]],
                    )
                    self.assertIn(
                        f'data-container-tag="{expected}" aria-pressed="true"',
                        render_versions(item),
                    )
                    del item["tags"][expected]
                else:
                    self.assertEqual(versions["releases"], [])
                    text = render_versions(item)
                    self.assertIn("No published images", text)
                    self.assertIn(item["image"] + ":latest", text)

    @patch.dict(os.environ, {"GH_IMAGE_VERSIONS_FIXTURE": ""})
    @patch("macros.main.collect")
    def test_live_macro(self, collect: Mock) -> None:
        """Use collected live data when no preview fixture is configured."""
        collect.return_value = IMAGE
        data = main.gh_image_versions_data("zrepl")
        collect.assert_called_once_with(REPOSITORY)
        self.assertFalse(data["preview"])
        self.assertEqual(len(data["releases"]), 2)

    @patch.dict(os.environ, {"GH_IMAGE_VERSIONS_FIXTURE": ""})
    @patch(
        "macros.main.collect",
        side_effect=HTTPError("https://ghcr.io/token", 403, "Forbidden", {}, None),
    )
    def test_fetch_failure_propagates(self, collect: Mock) -> None:
        """Surface upstream failures instead of rendering incomplete data."""
        with self.assertRaises(HTTPError):
            main.gh_image_versions_data("zrepl")
        collect.assert_called_once_with(REPOSITORY)

    def test_only_current_matching_aliases_are_shown(self) -> None:
        """Show aliases only beside the digest they currently reference."""
        item = copy.deepcopy(IMAGE)
        item["tags"]["latest"] = IMAGE["releases"][0]["digest"]
        del item["tags"]["stable"]
        item["tags"]["custom"] = IMAGE["releases"][1]["digest"]
        text = render_versions(item)
        stable = next(
            line for line in text.splitlines() if "/tag/v1.2.3-r1)" in line
        )
        preview = next(
            line for line in text.splitlines() if "/tag/v2.0.0-rc.1-r0)" in line
        )
        self.assertIn("<code>1.2.3-r1</code>", stable)
        self.assertIn("<code>custom</code>", stable)
        self.assertNotIn("<code>stable</code>", text)
        self.assertNotIn("<code>latest</code>", stable)
        self.assertIn("<code>latest</code>", preview)
        self.assertNotIn("<code>manual</code>", text)

    def test_all_verified_revisions_are_listed_newest_first(self) -> None:
        """Order every verified revision by publication time."""
        item = copy.deepcopy(IMAGE)
        older = {
            **item["releases"][1],
            "immutableTag": "1.2.3-r0",
            "revision": 0,
            "releaseTag": "v1.2.3-r0",
            "publishedAt": "2026-10-15T11:00:00Z",
        }
        item["releases"].insert(0, older)  # Selection must not depend on input order.
        item["tags"][older["immutableTag"]] = older["digest"]
        text = render_versions(item)
        self.assertEqual(text.count("\n### stable\n"), 1)
        self.assertEqual(text.count("\n### preview\n"), 1)
        self.assertEqual(text.count("| Image Tags | App Version | OS | Published |"), 2)
        self.assertNotIn("| Track |", text)
        self.assertLess(text.index("\n### stable\n"), text.index("\n### preview\n"))
        stable, preview = text.split("\n### stable\n")[1].split("\n### preview\n")
        self.assertEqual(preview.count("| <button"), 1)
        self.assertEqual(stable.count("| <button"), 2)
        self.assertIn('data-container-tag="1.2.3-r1"', text)
        self.assertIn('data-container-tag="1.2.3-r0"', text)
        self.assertIn("/releases/tag/v1.2.3-r0", text)
        self.assertLess(text.index("/tag/v1.2.3-r1"), text.index("/tag/v1.2.3-r0"))
        self.assertNotIn("container-versions-more", text)

    def test_tracks_are_sorted_alphabetically(self) -> None:
        """Sort track tables independently of release publication order."""
        item = copy.deepcopy(IMAGE)
        item["releases"][0]["track"] = "z-preview"
        item["releases"][1]["track"] = "a-stable"
        text = render_versions(item)
        self.assertLess(text.index("\n### a-stable\n"), text.index("\n### z-preview\n"))

    def test_stable_track_is_first(self) -> None:
        """Place stable before other tracks, even those earlier alphabetically."""
        item = copy.deepcopy(IMAGE)
        item["releases"][0]["track"] = "alpha"
        text = render_versions(item)
        self.assertLess(text.index("\n### stable\n"), text.index("\n### alpha\n"))

    def test_list_more_only_when_there_are_more_than_three_releases(self) -> None:
        """Render pagination controls only when releases exceed one page."""
        item = copy.deepcopy(IMAGE)
        for revision in range(4):
            release = {
                **IMAGE["releases"][1],
                "immutableTag": f"1.0.{revision}-r0",
                "releaseTag": f"v1.0.{revision}-r0",
                "version": f"1.0.{revision}",
                "publishedAt": f"2026-10-1{revision}T11:00:00Z",
            }
            item["releases"].append(release)
            item["tags"][release["immutableTag"]] = release["digest"]
        text = render_versions(item)
        self.assertIn('data-page-size="3"', text)
        self.assertIn('data-load-size="5"', text)
        self.assertIn(
            'class="md-button container-versions-more" hidden>List more</button>', text
        )
        stable, preview = text.split("\n### stable\n")[1].split("\n### preview\n")
        self.assertEqual(stable.count("| <button"), 5)
        self.assertEqual(preview.count("| <button"), 1)
        self.assertEqual(stable.count("container-versions-more"), 1)
        self.assertNotIn("container-versions-more", preview)
        # All rows are present for no-JavaScript access; JavaScript paginates them.
        self.assertIn("/tag/v1.0.0-r0", text)
        self.assertNotIn("container-versions-more", render_versions(IMAGE))

    def test_revision_tags_must_match_registry_digest(self) -> None:
        """Hide release rows with missing or mismatched registry tags."""
        for digest in (None, IMAGE["releases"][0]["digest"]):
            with self.subTest(digest=digest):
                item = copy.deepcopy(IMAGE)
                if digest is None:
                    del item["tags"]["1.2.3-r1"]
                else:
                    item["tags"]["1.2.3-r1"] = digest
                text = render_versions(item)
                self.assertNotIn("/releases/tag/v1.2.3-r1", text)
                self.assertNotIn("\n### stable\n", text)
                self.assertIn("\n### preview\n", text)

    def test_tag_buttons_and_published_release_links(self) -> None:
        """Render ordered tag buttons and links to their published releases."""
        text = render_versions(IMAGE)
        self.assertNotIn("Image: ", text)
        self.assertNotIn("Last refreshed:", text)
        self.assertNotIn("build-time snapshot", text)
        self.assertIn(
            "[2026-10-16 11:00]"
            "(https://github.com/tuxcrate/zrepl/releases/tag/v1.2.3-r1)",
            text,
        )
        stable = next(
            line for line in text.splitlines() if "/tag/v1.2.3-r1)" in line
        )
        tags = ["1.2.3-r1", "1.2.3", "1.2", "latest", "stable"]
        positions = [stable.index(f'data-container-tag="{tag}"') for tag in tags]
        self.assertEqual(positions, sorted(positions))
        self.assertEqual(stable.count('type="button"'), len(tags))
        self.assertEqual(
            stable.count('data-container-image="ghcr.io/tuxcrate/zrepl"'), len(tags)
        )
        self.assertIn('data-container-tag="latest" aria-pressed="false"', stable)
        self.assertIn('data-container-tag="1.2.3-r1" aria-pressed="true"', stable)
        self.assertEqual(text.count('aria-pressed="true"'), 1)
        self.assertIn('data-container-tag="2.0.0-rc.1-r0" aria-pressed="false"', text)
        self.assertNotIn("[GHCR]", text)

    def test_escaping_and_empty_image(self) -> None:
        """Escape table delimiters and render a clear empty-image message."""
        self.assertEqual(
            main.cell("<script>|`[x]\n"), "&lt;script&gt;&#124;&#96;&#91;x&#93; "
        )
        item = {**IMAGE, "tags": {}, "releases": [], "legacyReleases": []}
        text = render_versions(item)
        self.assertIn(
            "No published images with matching release metadata are available yet", text
        )
        self.assertNotIn("| Track |", text)

    def test_os_column_formats_release_metadata(self) -> None:
        """Title-case the OS flavor and append the OS version."""
        for flavor, version, expected in (
            ("debian", "13.7", "Debian/13.7"),
            ("alpine", "3.22", "Alpine/3.22"),
            ("openSUSE", "16.0", "Opensuse/16.0"),
        ):
            with self.subTest(flavor=flavor):
                item = copy.deepcopy(IMAGE)
                item["releases"][0].update(os_flavor=flavor, os_version=version)
                text = render_versions(item)
                self.assertIn(f"| {expected} |", text)
                self.assertIn("| <code>1.2.3</code> | — |", text)

    def test_os_column_handles_missing_metadata(self) -> None:
        """Keep older releases visible when OS metadata is absent or incomplete."""
        for fields in (
            {},
            {"os_flavor": "debian"},
            {"os_version": "13.7"},
            {"os_flavor": "", "os_version": "13.7"},
            {"os_flavor": "debian", "os_version": None},
        ):
            with self.subTest(fields=fields):
                item = copy.deepcopy(IMAGE)
                item["releases"][0].update(fields)
                text = render_versions(item)
                self.assertIn("| <code>2.0.0-rc.1</code> | — |", text)

    def test_template_escapes_table_values(self) -> None:
        """Prevent release metadata from injecting HTML or table syntax."""
        item = copy.deepcopy(IMAGE)
        item["releases"][0]["track"] = "<script>|`[x]\n"
        item["releases"][0]["version"] = '<img src=x onerror="alert(1)">'
        item["releases"][0]["os_flavor"] = "<script>|"
        item["releases"][0]["os_version"] = "<img>|"
        text = render_versions(item)
        self.assertIn("&lt;script&gt;&#124;&#96;&#91;x&#93; ", text)
        self.assertIn(
            "<code>&lt;img src=x onerror=&quot;alert(1)&quot;&gt;</code>", text
        )
        self.assertNotIn("<script>", text)
        self.assertNotIn("<img ", text)
        self.assertIn("| &lt;Script&gt;&#124;/&lt;img&gt;&#124; |", text)


class ContainerTemplateTests(unittest.TestCase):
    """Check shared container layouts and command rendering."""

    def test_docker_run_preserves_shell_fragments(self) -> None:
        """Keep shell quoting and expansions unchanged in CLI examples."""
        arguments = [
            "--rm",
            '--user "$(id -u):$(id -g)"',
            '--mount "type=bind,src=$PWD/downloads,dst=/downloads"',
            "ghcr.io/tuxcrate/gallery-dl:latest",
            "'https://example.com/gallery'",
        ]
        self.assertEqual(
            main.docker_run(arguments), "docker run \\\n  " + " \\\n  ".join(arguments)
        )

    def test_invalid_docker_run(self) -> None:
        """Reject empty, non-string, and multiline shell fragments."""
        for arguments in (
            None,
            "--rm",
            [],
            [1],
            [""],
            [" "],
            ["--rm\nwhoami"],
            ["--rm\r"],
        ):
            with self.subTest(arguments=arguments), self.assertRaises(ValueError):
                main.docker_run(arguments)

    def test_compose_round_trip_and_order(self) -> None:
        """Preserve Compose values while ordering common service properties."""
        configuration = {
            "services": {
                "app": {
                    "image": "ghcr.io/tuxcrate/app:latest",
                    "user": "${UID}:${GID}",
                    "restart": "no",
                    "ports": ["8080:80"],
                    "command": ["https://example.com/gallery"],
                }
            }
        }
        text = main.compose_yaml(configuration)
        self.assertEqual(yaml.safe_load(text), configuration)
        self.assertLess(text.index("image:"), text.index("user:"))
        self.assertLess(text.index("user:"), text.index("restart:"))
        self.assertNotIn("{", text.replace("${UID}:${GID}", ""))

    def test_compose_service_property_order(self) -> None:
        """Apply the shared property order independently to each service."""
        keys = [
            "image",
            "build",
            "container_name",
            "hostname",
            "user",
            "restart",
            "init",
            "entrypoint",
            "command",
            "working_dir",
            "environment",
            "env_file",
            "ports",
            "expose",
            "volumes",
            "devices",
            "networks",
            "depends_on",
            "healthcheck",
        ]
        configuration = {
            "services": {
                "app": {key: key for key in reversed(keys)},
                "worker": {
                    "command": ["work"],
                    "restart": "no",
                    "image": "worker:latest",
                },
            }
        }
        rendered = yaml.safe_load(main.compose_yaml(configuration))
        self.assertEqual(rendered, configuration)
        self.assertEqual(list(rendered["services"]), ["app", "worker"])
        self.assertEqual(list(rendered["services"]["app"]), keys)
        self.assertEqual(
            list(rendered["services"]["worker"]), ["image", "restart", "command"]
        )

    def test_compose_preserves_unknown_properties_nested_order_and_input(self) -> None:
        """Preserve extension properties, nested order, and the original input."""
        configuration = {
            "name": "example",
            "services": {
                "app": {
                    "x-custom": {"z": 1, "a": 2},
                    "environment": {"Z_VAR": "last", "A_VAR": "first"},
                    "volumes": ["./z:/z", "./a:/a"],
                    "command": ["serve", "--verbose"],
                    "read_only": True,
                    "image": "app:latest",
                }
            },
            "volumes": {"z": {}, "a": {}},
        }
        before = yaml.safe_dump(configuration, sort_keys=False)
        rendered = yaml.safe_load(main.compose_yaml(configuration))
        service = rendered["services"]["app"]
        self.assertEqual(rendered, configuration)
        self.assertEqual(list(rendered), ["name", "services", "volumes"])
        self.assertEqual(
            list(service),
            ["image", "command", "environment", "volumes", "x-custom", "read_only"],
        )
        self.assertEqual(list(service["environment"]), ["Z_VAR", "A_VAR"])
        self.assertEqual(list(service["x-custom"]), ["z", "a"])
        self.assertEqual(list(rendered["volumes"]), ["z", "a"])
        self.assertEqual(yaml.safe_dump(configuration, sort_keys=False), before)

    def test_invalid_compose(self) -> None:
        """Reject Compose data without a valid services mapping."""
        for configuration in (None, [], "services: {}", {}, {"services": []}):
            with (
                self.subTest(configuration=configuration),
                self.assertRaises(ValueError),
            ):
                main.compose_yaml(configuration)

    def test_container_pages_use_shared_layout(self) -> None:
        """Render all container pages through the shared usage layout."""
        root = Path(__file__).resolve().parents[2]
        env = template_environment()
        versions = Mock(
            return_value={
                "image": IMAGE["image"],
                "preview": False,
                "releases": [
                    {
                        **IMAGE["releases"][1],
                        "immutableTag": "0.7.0-r5",
                        "tags": ["0.7.0-r5"],
                    }
                ],
            }
        )
        env.globals["gh_image_versions_data"] = versions
        for name in ("gallery-dl", "zrepl", "sonarr"):
            with self.subTest(name=name):
                versions.reset_mock()
                source = (root / "docs/containers" / f"{name}.md").read_text()
                _, front_matter, body = source.split("---", 2)
                metadata = yaml.safe_load(front_matter)
                versions.return_value["image"] = (
                    "ghcr.io/" + metadata["container"]["repository"]
                )
                text = env.from_string(body).render(page={"meta": metadata})
                self.assertIn(f"# {metadata['title']}", text)
                self.assertIn(f'!!! info "About {metadata["title"]}"', text)
                self.assertIn("    " + metadata["container"]["description"], text)
                self.assertEqual(text.count("{ .md-button .container-link "), 3)
                for button in ("upstream", "source", "registry"):
                    self.assertIn(f".container-link--{button}", text)
                self.assertIn('=== ":lucide-terminal: CLI"', text)
                self.assertIn('=== ":simple-docker: Compose"', text)
                self.assertIn('```sh linenums="1"', text)
                self.assertIn('```yaml linenums="1"', text)
                self.assertIn("    docker run \\", text)
                self.assertIn("    services:", text)
                self.assertIn(
                    f'<div class="container-usage" data-container-image="ghcr.io/'
                    f'{metadata["container"]["repository"]}" markdown="1">',
                    text,
                )
                self.assertLess(
                    text.index("## Published versions"), text.index("## Usage")
                )
                versions.assert_called_once_with(f"tuxcrate/{name}")
                self.assertEqual(text.count(f"ghcr.io/tuxcrate/{name}:0.7.0-r5"), 2)
                self.assertNotIn(f"ghcr.io/tuxcrate/{name}:latest", text)
                self.assertIn("| Image Tags | App Version | OS | Published |", text)
                self.assertNotIn("| Image Tags | Track |", text)
                self.assertNotIn("No image has been published yet", text)
                if name == "zrepl":
                    self.assertIn("--privileged", metadata["container"]["docker_run"])
                    privileged = metadata["container"]["compose"]["services"]["zrepl"][
                        "privileged"
                    ]
                    self.assertIs(privileged, True)  # noqa: FBT003 -- Verify the boolean type too.
                    self.assertIn("--privileged", text)
                    self.assertIn("privileged: true", text)

    @patch.dict(os.environ, {"GH_IMAGE_VERSIONS_FIXTURE": str(FIXTURE)})
    @patch(
        "macros.main.request",
        side_effect=AssertionError("Offline preview used the network"),
    )
    def test_gallery_dl_offline_table(self, request: Mock) -> None:
        """Render gallery-dl fixture versions without network access."""
        root = Path(__file__).resolve().parents[2]
        source = (root / "docs/containers/gallery-dl.md").read_text()
        _, front_matter, body = source.split("---", 2)
        text = (
            template_environment()
            .from_string(body)
            .render(page={"meta": yaml.safe_load(front_matter)})
        )
        self.assertIn("fictional test data", text)
        self.assertIn("| Image Tags | App Version | OS | Published |", text)
        self.assertEqual(text.count("ghcr.io/tuxcrate/gallery-dl:1.2.3-r0"), 2)
        request.assert_not_called()

    @patch.dict(os.environ, {"GH_IMAGE_VERSIONS_FIXTURE": str(FIXTURE)})
    def test_preview_fixture_has_paginated_stable_tables(self) -> None:
        """Keep enough valid dummy releases to exercise two load-more clicks."""
        for item in (
            item for item in SNAPSHOT["images"]
            if item["repository"] in (REPOSITORY, "tuxcrate/gallery-dl")
        ):
            with self.subTest(repository=item["repository"]):
                for release in item["releases"]:
                    main.validate_release(release, item["image"], release["releaseTag"])
                versions = main.gh_image_versions_data(item["repository"])
                stable = [
                    release
                    for release in versions["releases"]
                    if release["track"] == "stable"
                ]
                self.assertGreaterEqual(len(stable), 10)
                text = render_versions(item)
                table = text.split("\n### stable\n")[1].split("</div>")[0]
                self.assertEqual(table.count("| <button"), len(stable))
                self.assertIn("container-versions-more", table)
                self.assertIn("| — |", table)
                self.assertIn(
                    "| Debian/13.7 |"
                    if item["repository"] == REPOSITORY
                    else "| Alpine/3.22.2 |",
                    table,
                )

    @patch.dict(os.environ, {"GH_IMAGE_VERSIONS_FIXTURE": str(FIXTURE)})
    @patch(
        "macros.main.request",
        side_effect=AssertionError("Offline preview used the network"),
    )
    def test_template_renders_default_revision_without_javascript(
        self, request: Mock
    ) -> None:
        """Include the selected immutable revision in server-rendered examples."""
        root = Path(__file__).resolve().parents[2]
        env = template_environment()
        source = (root / "docs/containers/zrepl.md").read_text()
        _, front_matter, body = source.split("---", 2)
        metadata = yaml.safe_load(front_matter)
        text = env.from_string(body).render(page={"meta": metadata})
        self.assertIn('data-container-tag="1.2.3-r1" aria-pressed="true"', text)
        self.assertEqual(text.count("ghcr.io/tuxcrate/zrepl:1.2.3-r1"), 2)
        self.assertNotIn("ghcr.io/tuxcrate/zrepl:latest", text)
        self.assertIn("fictional test data", text)
        self.assertIn("| Image Tags | App Version | OS | Published |", text)
        self.assertIn("| <code>1.2.3</code> | — | [2026-10-16 11:00]", text)
        self.assertNotIn("<code>manual</code>", text)
        self.assertNotIn("v1.0.0-r0", text)
        self.assertNotIn("sha256:", text)
        request.assert_not_called()


    @patch.dict(os.environ, {"GH_IMAGE_VERSIONS_FIXTURE": str(FIXTURE)})
    def test_sonarr_tracks_default_to_stable(self) -> None:
        """Render numeric prereleases without selecting one by default."""
        item = next(
            item for item in SNAPSHOT["images"]
            if item["repository"] == "tuxcrate/sonarr"
        )
        for release in item["releases"]:
            main.validate_release(release, item["image"], release["releaseTag"])
        self.assertEqual(item["tags"]["latest"], item["tags"]["4.0.20.3014-r0"])
        root = Path(__file__).resolve().parents[2]
        source = (root / "docs/containers/sonarr.md").read_text()
        _, front_matter, body = source.split("---", 2)
        text = template_environment().from_string(body).render(
            page={"meta": yaml.safe_load(front_matter)}
        )
        self.assertIn("### develop", text)
        self.assertIn('data-container-tag="4.0.20.3014-r0" aria-pressed="true"', text)
        self.assertIn('data-container-tag="5.0.0.2668-r0" aria-pressed="false"', text)
        self.assertEqual(text.count("ghcr.io/tuxcrate/sonarr:4.0.20.3014-r0"), 2)
        self.assertIn("read_only: true", text)
        self.assertIn("--cap-drop=ALL", text)


class SourceTests(unittest.TestCase):
    """Check release validation and HTTP credential boundaries."""

    @patch("macros.main.build_opener")
    def test_reject_non_https_requests(self, opener: Mock) -> None:
        """Reject unsafe URL schemes before constructing a network opener."""
        for url in ("http://example.com", "file:///etc/passwd", "ftp://example.com"):
            with self.subTest(url=url), self.assertRaisesRegex(ValueError, "non-HTTPS"):
                main.request(url)
        opener.assert_not_called()

    @patch("macros.main.build_opener")
    def test_http_error_includes_source_url(self, opener: Mock) -> None:
        """Include the request URL and HTTP status in upstream failures."""
        opener.return_value.open.side_effect = HTTPError(
            "https://ghcr.io/token", 403, "Forbidden", {}, None
        )
        with self.assertRaisesRegex(
            RuntimeError, "GET https://ghcr.io/token: HTTP 403"
        ):
            main.request("https://ghcr.io/token")

    @patch.dict(os.environ, {"GH_TOKEN": "github-secret"})
    @patch("macros.main.request")
    def test_paginated_releases_and_registry_tags(self, request: Mock) -> None:
        """Follow API pagination without forwarding credentials to assets."""
        record = {
            key: value
            for key, value in IMAGE["releases"][1].items()
            if key not in ("releaseTag", "publishedAt")
        }
        release = {
            "draft": False,
            "tag_name": "v1.2.3-r1",
            "published_at": "2026-10-16T11:00:00Z",
            "assets": [
                {
                    "name": "release.json",
                    "browser_download_url": "https://github.com/tuxcrate/zrepl/releases/download/v1.2.3-r1/release.json",
                }
            ],
        }
        request.side_effect = [
            (
                [{**release, "draft": True}],
                {
                    "Link": (
                        "<https://api.github.com/repos/"
                        "tuxcrate/zrepl/releases?page=2>; "
                        'rel="next"'
                    )
                },
            ),
            ([release, {**release, "tag_name": "v0.1", "assets": []}], {}),
            (record, {}),
            ({"token": "registry-secret"}, {}),
            (
                {"tags": ["latest"]},
                {"Link": '</v2/tuxcrate/zrepl/tags/list?last=latest>; rel="next"'},
            ),
            (None, {"Docker-Content-Digest": record["digest"]}),
            ({"tags": ["1.2.3-r1"]}, {}),
            (None, {"Docker-Content-Digest": record["digest"]}),
        ]
        item = main.collect(REPOSITORY)
        self.assertEqual(
            item["tags"], {"latest": record["digest"], "1.2.3-r1": record["digest"]}
        )
        self.assertEqual(len(item["releases"]), 1)
        self.assertEqual(item["legacyReleases"], ["v0.1"])
        calls = request.call_args_list
        self.assertEqual(
            calls[0].kwargs["headers"]["Authorization"], "Bearer github-secret"
        )
        self.assertEqual(calls[2].kwargs, {})  # No API credentials on public assets.
        self.assertEqual(
            calls[4].kwargs["headers"]["Authorization"], "Bearer registry-secret"
        )
        self.assertEqual(calls[5].kwargs["method"], "HEAD")

    @patch("macros.main.request")
    def test_reject_cross_origin_pagination(self, request: Mock) -> None:
        """Reject pagination links that could leak credentials to another host."""
        request.return_value = (
            [],
            {"Link": '<https://evil.example/steal>; rel="next"'},
        )
        with self.assertRaisesRegex(ValueError, "cross-origin"):
            list(
                main.pages(
                    "https://api.github.com/releases", {"Authorization": "secret"}
                )
            )
        self.assertEqual(request.call_count, 1)

    @patch("macros.main.request")
    def test_reject_pagination_loop(self, request: Mock) -> None:
        """Stop following pagination links when a URL repeats."""
        request.return_value = (
            [],
            {"Link": '<https://api.github.com/releases>; rel="next"'},
        )
        with self.assertRaisesRegex(ValueError, "Repeated"):
            list(main.pages("https://api.github.com/releases", {}))

    @patch("macros.main.request")
    def test_reject_unexpected_asset_url(self, request: Mock) -> None:
        """Reject release assets outside the expected GitHub download path."""
        request.return_value = (
            [
                {
                    "draft": False,
                    "assets": [
                        {
                            "name": "release.json",
                            "browser_download_url": "https://evil.example/release.json",
                        }
                    ],
                }
            ],
            {},
        )
        with self.assertRaisesRegex(ValueError, "asset URL"):
            main.collect(REPOSITORY)
        request.assert_called_once()

    def test_validate_metadata(self) -> None:
        """Accept valid metadata and reject malformed release fields."""
        record = IMAGE["releases"][1]
        main.validate_release(record, IMAGE["image"], record["releaseTag"])
        for change in (
            {"revision": None},
            {"revision": True},
            {"revision": -1},
            {"revision": 1.5},
            {"immutableTag": "1.2.3-r0"},
            {"digest": "not-a-digest"},
            {"image": "ghcr.io/other/image"},
            {"platforms": "linux/amd64"},
            {"schemaVersion": 2},
        ):
            with self.subTest(change=change), self.assertRaises(ValueError):
                main.validate_release(
                    {**record, **change}, IMAGE["image"], record["releaseTag"]
                )

    def test_redirect_strips_credentials(self) -> None:
        """Keep authorization only on same-host HTTPS redirects."""
        request = Request(
            "https://api.github.com/asset", headers={"Authorization": "secret"}
        )
        redirected = main.SafeRedirect().redirect_request(
            request, None, 302, "Found", {}, "https://assets.example/asset"
        )
        self.assertIsNone(redirected.get_header("Authorization"))
        redirected = main.SafeRedirect().redirect_request(
            request, None, 302, "Found", {}, "https://api.github.com/other"
        )
        self.assertEqual(redirected.get_header("Authorization"), "secret")
        with self.assertRaises(ValueError):
            main.SafeRedirect().redirect_request(
                request, None, 302, "Found", {}, "http://example.com"
            )


if __name__ == "__main__":
    unittest.main()
