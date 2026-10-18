"""Build-time Zensical macros for public Tuxcrate container images."""

import html
import json
import os
import re
from collections.abc import Callable, Iterator, Mapping
from email.message import Message
from http.client import HTTPResponse
from pathlib import Path
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

import yaml

type Metadata = dict[str, Any]


class MacroEnvironment(Protocol):
    """Registration interface provided by the Zensical macro environment."""

    def macro(self, function: Callable[..., object]) -> None:
        """Register a template macro."""
        ...

    def filter(self, function: Callable[..., object]) -> None:
        """Register a template filter."""
        ...


TAG = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}")
DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
CONTAINERS_DIR = Path(__file__).resolve().parents[1] / "docs/containers"
ACCEPT_MANIFEST = (
    "application/vnd.oci.image.index.v1+json, "
    "application/vnd.oci.image.manifest.v1+json, "
    "application/vnd.docker.distribution.manifest.list.v2+json, "
    "application/vnd.docker.distribution.manifest.v2+json"
)


class SafeRedirect(HTTPRedirectHandler):
    """Keep redirects on HTTPS and strip credentials when changing hosts."""

    # The positional signature is defined by urllib's redirect handler.
    def redirect_request(  # noqa: PLR0913, PLR0917
        self,
        request: Request,
        response: HTTPResponse | None,
        code: int,
        message: str,
        headers: Message | Mapping[str, str],
        url: str,
    ) -> Request | None:
        """Follow HTTPS redirects without leaking cross-host authorization."""
        if urlsplit(url).scheme != "https":
            msg = "Refusing a non-HTTPS redirect"
            raise ValueError(msg)
        redirected = super().redirect_request(
            request, response, code, message, headers, url
        )
        if redirected and urlsplit(url).netloc != urlsplit(request.full_url).netloc:
            redirected.remove_header("Authorization")
        return redirected


def request(
    url: str, *, headers: Mapping[str, str] | None = None, method: str = "GET"
) -> tuple[Metadata | list[Metadata] | None, Message]:
    """Fetch bounded JSON responses or manifest headers from HTTPS sources."""
    if urlsplit(url).scheme != "https":
        message = "Refusing a non-HTTPS request"
        raise ValueError(message)
    req = Request(  # noqa: S310 -- The URL scheme is checked above.
        url,
        headers={"User-Agent": "tuxcrate-website", **(headers or {})},
        method=method,
    )
    try:
        response = build_opener(SafeRedirect()).open(req, timeout=60)
    except HTTPError as error:
        msg = f"{method} {url}: HTTP {error.code}"
        raise RuntimeError(msg) from error
    except URLError as error:
        msg = f"{method} {url}: {error.reason}"
        raise RuntimeError(msg) from error
    with response:
        if method == "HEAD":
            return None, response.headers
        data = response.read(32 * 1024 * 1024 + 1)
        if len(data) > 32 * 1024 * 1024:
            msg = f"Response too large: {url}"
            raise ValueError(msg)
        return json.loads(data), response.headers


def pages(url: str, headers: Mapping[str, str]) -> Iterator[Metadata | list[Metadata]]:
    """Yield API pages while rejecting repeated or cross-origin links."""
    seen = set()
    while url:
        if url in seen:
            msg = "Repeated pagination link"
            raise ValueError(msg)
        seen.add(url)
        data, response_headers = request(url, headers=headers)
        yield data
        match = re.search(r'<([^>]+)>;\s*rel="next"', response_headers.get("Link", ""))
        next_url = urljoin(url, match[1]) if match else ""
        if next_url:
            target, origin = urlsplit(next_url), urlsplit(url)
            if (
                target.scheme != "https"
                or target.netloc != origin.netloc
                or target.username
            ):
                msg = "Refusing cross-origin pagination link"
                raise ValueError(msg)
        url = next_url


def validate_release(record: Metadata, image: str, release_tag: str) -> None:
    """Check release metadata against its image, tag, digest, and platforms."""
    revision = record.get("revision")
    if (
        record.get("schemaVersion") != 1
        or record.get("image") != image
        or type(revision) is not int
        or revision < 0
    ):
        msg = "Unsupported or mismatched release metadata"
        raise ValueError(msg)
    for key in ("track", "version", "immutableTag"):
        if not isinstance(record.get(key), str) or not TAG.fullmatch(record[key]):
            msg = f"Invalid release {key}"
            raise ValueError(msg)
    if (
        record["immutableTag"] != f"{record['version']}-r{revision}"
        or release_tag != f"v{record['immutableTag']}"
        or not DIGEST.fullmatch(record.get("digest", ""))
    ):
        msg = "Release tag or digest does not match metadata"
        raise ValueError(msg)
    if not isinstance(record.get("platforms"), list) or not all(
        isinstance(platform, str) for platform in record["platforms"]
    ):
        msg = "Invalid release platforms"
        raise ValueError(msg)


def collect_releases(repository: str, image: str) -> tuple[list[Metadata], list[str]]:
    """Collect validated GitHub releases and names of legacy releases."""
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    releases, legacy = [], []
    for page in pages(
        f"https://api.github.com/repos/{repository}/releases?per_page=100", headers
    ):
        for release in page:
            if release["draft"]:
                continue
            assets = [
                asset for asset in release["assets"] if asset["name"] == "release.json"
            ]
            if not assets:
                legacy.append(release["tag_name"])
                continue
            if len(assets) != 1:
                msg = "Duplicate release.json assets"
                raise ValueError(msg)
            url = assets[0]["browser_download_url"]
            parsed = urlsplit(url)
            if (
                parsed.scheme != "https"
                or parsed.netloc != "github.com"
                or not parsed.path.startswith(f"/{repository}/releases/download/")
                or not parsed.path.endswith("/release.json")
            ):
                msg = "Unexpected release asset URL"
                raise ValueError(msg)
            # Public release downloads never receive the GitHub API token.
            record, _ = request(url)
            validate_release(record, image, release["tag_name"])
            releases.append(
                {
                    **record,
                    "releaseTag": release["tag_name"],
                    "publishedAt": release["published_at"],
                }
            )
    releases.sort(key=lambda record: record["publishedAt"], reverse=True)
    return releases, legacy


def collect_tags(repository: str, image: str) -> dict[str, str]:
    """Resolve registry tags to verified manifest digests."""
    query = urlencode({"service": "ghcr.io", "scope": f"repository:{repository}:pull"})
    credentials, _ = request(f"https://ghcr.io/token?{query}")
    headers = {
        "Authorization": f"Bearer {credentials['token']}",
        "Accept": ACCEPT_MANIFEST,
    }
    tags = {}
    for page in pages(f"https://ghcr.io/v2/{repository}/tags/list?n=100", headers):
        for tag in page.get("tags") or []:
            if not TAG.fullmatch(tag):
                msg = "Invalid registry tag"
                raise ValueError(msg)
            if tag in tags:
                continue
            _, response_headers = request(
                f"https://ghcr.io/v2/{repository}/manifests/{quote(tag, safe='')}",
                headers=headers,
                method="HEAD",
            )
            digest = response_headers.get("Docker-Content-Digest", "")
            if not DIGEST.fullmatch(digest):
                msg = f"Invalid digest for {image}:{tag}"
                raise ValueError(msg)
            tags[tag] = digest
    return tags


def collect(repository: str) -> Metadata:
    """Collect release metadata and current registry digests for an image."""
    image = f"ghcr.io/{repository}"
    releases, legacy = collect_releases(repository, image)
    # A new repository may not have a GHCR package until its first release.
    tags = collect_tags(repository, image) if releases else {}
    return {
        "repository": repository,
        "image": image,
        "releases": releases,
        "legacyReleases": legacy,
        "tags": tags,
    }


def cell(value: object) -> str:
    """Escape HTML and Markdown delimiters for a table cell."""
    text = html.escape(str(value))
    for source, replacement in (
        ("|", "&#124;"),
        ("`", "&#96;"),
        ("[", "&#91;"),
        ("]", "&#93;"),
        ("\n", " "),
        ("\r", " "),
    ):
        text = text.replace(source, replacement)
    return text


def published_releases(item: Metadata) -> Iterator[Metadata]:
    """Yield all verified releases, newest first."""
    for release in sorted(
        item["releases"], key=lambda record: record["publishedAt"], reverse=True
    ):
        if item["tags"].get(release["immutableTag"]) != release["digest"]:
            continue
        yield release


def gh_image_versions_data(name: str) -> Metadata:
    """Return structured, verified releases and their current tags for the template."""
    repository = name if "/" in name else f"tuxcrate/{name}"
    if not re.fullmatch(r"[a-z0-9][a-z0-9_.-]*/[a-z0-9][a-z0-9_.-]*", repository):
        msg = "Expected a lowercase repository name or owner/name"
        raise ValueError(msg)
    fixture = os.environ.get("GH_IMAGE_VERSIONS_FIXTURE")
    if fixture:
        snapshot = json.loads(Path(fixture).read_text())
        item = next(
            item for item in snapshot["images"] if item["repository"] == repository
        )
    else:
        item = collect(repository)
    releases = []
    for release in published_releases(item):
        aliases = sorted(
            (
                tag
                for tag, digest in item["tags"].items()
                if digest == release["digest"] and tag != release["immutableTag"]
            ),
            key=lambda tag: (tag != release["version"], tag),
        )
        releases.append({**release, "tags": [release["immutableTag"], *aliases]})
    return {
        "image": item["image"],
        "releases": releases,
        "preview": bool(fixture),
    }


def docker_run(arguments: list[str]) -> str:
    """Format shell fragments without changing their quoting or expansions."""
    if (
        not isinstance(arguments, list)
        or not arguments
        or not all(
            isinstance(arg, str) and arg.strip() and "\n" not in arg and "\r" not in arg
            for arg in arguments
        )
    ):
        msg = "docker_run must be a nonempty list of single-line shell fragments"
        raise ValueError(msg)
    command = " \\\n  ".join(arguments)
    return f"docker run \\\n  {command}"


def compose_yaml(configuration: Metadata) -> str:
    """Render block-style Compose YAML with a consistent service property order."""
    if not isinstance(configuration, dict) or not isinstance(
        configuration.get("services"), dict
    ):
        # Keep malformed template data on the same ValueError path as other macros.
        msg = "compose must be a mapping with a services mapping"
        raise ValueError(msg)  # noqa: TRY004
    service_keys = (
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
    )
    services = {}
    for name, service in configuration["services"].items():
        if isinstance(service, dict):
            ordered = {key: service[key] for key in service_keys if key in service}
            ordered.update(
                (key, value) for key, value in service.items() if key not in ordered
            )
            services[name] = ordered
        else:
            services[name] = service
    configuration = {**configuration, "services": services}
    return yaml.safe_dump(
        configuration, sort_keys=False, default_flow_style=False
    ).rstrip()


def container_pages() -> list[Metadata]:
    """Discover image pages and reuse their front matter for the container index."""
    images = []
    for path in CONTAINERS_DIR.rglob("*.md"):
        text = path.read_text()
        front_matter = re.match(r"\A---\r?\n(.*?)\r?\n---(?:\r?\n|\Z)", text, re.DOTALL)
        if not front_matter:
            continue
        metadata = yaml.safe_load(front_matter[1])
        if not isinstance(metadata, dict) or "container" not in metadata:
            continue
        images.append(
            {
                "title": metadata["title"],
                "description": metadata["container"]["description"],
                "url": quote(path.relative_to(CONTAINERS_DIR).as_posix(), safe="/"),
            }
        )
    return sorted(images, key=lambda image: image["title"].casefold())


def define_env(env: MacroEnvironment) -> None:
    """Register the container macro and rendering filters with Zensical."""
    env.macro(gh_image_versions_data)
    env.macro(container_pages)
    env.filter(cell)
    env.filter(docker_run)
    env.filter(compose_yaml)
