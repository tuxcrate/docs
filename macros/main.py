"""Build-time Zensical macros for public Tuxcrate container images."""

import html
import json
import os
import re
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

import yaml

TAG = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}")
DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
ACCEPT_MANIFEST = ", ".join((
    "application/vnd.oci.image.index.v1+json",
    "application/vnd.oci.image.manifest.v1+json",
    "application/vnd.docker.distribution.manifest.list.v2+json",
    "application/vnd.docker.distribution.manifest.v2+json",
))


class SafeRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, url):
        if urlsplit(url).scheme != "https":
            raise ValueError("Refusing a non-HTTPS redirect")
        redirected = super().redirect_request(request, response, code, message, headers, url)
        if redirected and urlsplit(url).netloc != urlsplit(request.full_url).netloc:
            redirected.remove_header("Authorization")
        return redirected


def request(url, *, headers=None, method="GET"):
    req = Request(url, headers={"User-Agent": "tuxcrate-website", **(headers or {})}, method=method)
    try:
        response = build_opener(SafeRedirect()).open(req, timeout=60)
    except HTTPError as error:
        raise RuntimeError(f"{method} {url}: HTTP {error.code}") from error
    except URLError as error:
        raise RuntimeError(f"{method} {url}: {error.reason}") from error
    with response:
        if method == "HEAD":
            return None, response.headers
        data = response.read(32 * 1024 * 1024 + 1)
        if len(data) > 32 * 1024 * 1024:
            raise ValueError(f"Response too large: {url}")
        return json.loads(data), response.headers


def pages(url, headers):
    seen = set()
    while url:
        if url in seen:
            raise ValueError("Repeated pagination link")
        seen.add(url)
        data, response_headers = request(url, headers=headers)
        yield data
        match = re.search(r'<([^>]+)>;\s*rel="next"', response_headers.get("Link", ""))
        next_url = urljoin(url, match[1]) if match else ""
        if next_url:
            target, origin = urlsplit(next_url), urlsplit(url)
            if target.scheme != "https" or target.netloc != origin.netloc or target.username:
                raise ValueError("Refusing cross-origin pagination link")
        url = next_url


def validate_release(record, image, release_tag):
    revision = record.get("revision")
    if (record.get("schemaVersion") != 1 or record.get("image") != image
            or type(revision) is not int or revision < 0):
        raise ValueError("Unsupported or mismatched release metadata")
    for key in ("track", "version", "immutableTag"):
        if not isinstance(record.get(key), str) or not TAG.fullmatch(record[key]):
            raise ValueError(f"Invalid release {key}")
    if (record["immutableTag"] != f'{record["version"]}-r{revision}'
            or release_tag != f'v{record["immutableTag"]}'
            or not DIGEST.fullmatch(record.get("digest", ""))):
        raise ValueError("Release tag or digest does not match metadata")
    if not isinstance(record.get("platforms"), list) or not all(
        isinstance(platform, str) for platform in record["platforms"]
    ):
        raise ValueError("Invalid release platforms")


def collect(repository):
    image = f"ghcr.io/{repository}"
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    releases, legacy = [], []
    for page in pages(f"https://api.github.com/repos/{repository}/releases?per_page=100", headers):
        for release in page:
            if release["draft"]:
                continue
            assets = [asset for asset in release["assets"] if asset["name"] == "release.json"]
            if not assets:
                legacy.append(release["tag_name"])
                continue
            if len(assets) != 1:
                raise ValueError("Duplicate release.json assets")
            url = assets[0]["browser_download_url"]
            parsed = urlsplit(url)
            if (parsed.scheme != "https" or parsed.netloc != "github.com"
                    or not parsed.path.startswith(f"/{repository}/releases/download/")
                    or not parsed.path.endswith("/release.json")):
                raise ValueError("Unexpected release asset URL")
            # Public release downloads never receive the GitHub API token.
            record, _ = request(url)
            validate_release(record, image, release["tag_name"])
            releases.append({**record, "releaseTag": release["tag_name"],
                             "publishedAt": release["published_at"]})
    releases.sort(key=lambda record: record["publishedAt"], reverse=True)

    query = urlencode({"service": "ghcr.io", "scope": f"repository:{repository}:pull"})
    credentials, _ = request(f"https://ghcr.io/token?{query}")
    headers = {"Authorization": f'Bearer {credentials["token"]}', "Accept": ACCEPT_MANIFEST}
    tags = {}
    for page in pages(f"https://ghcr.io/v2/{repository}/tags/list?n=100", headers):
        for tag in page.get("tags") or []:
            if not TAG.fullmatch(tag):
                raise ValueError("Invalid registry tag")
            if tag in tags:
                continue
            _, response_headers = request(
                f"https://ghcr.io/v2/{repository}/manifests/{quote(tag, safe='')}",
                headers=headers, method="HEAD",
            )
            digest = response_headers.get("Docker-Content-Digest", "")
            if not DIGEST.fullmatch(digest):
                raise ValueError(f"Invalid digest for {image}:{tag}")
            tags[tag] = digest
    return {"repository": repository, "image": image, "releases": releases,
            "legacyReleases": legacy, "tags": tags}


def cell(value):
    text = html.escape(str(value))
    for source, replacement in (("|", "&#124;"), ("`", "&#96;"), ("[", "&#91;"),
                                ("]", "&#93;"), ("\n", " "), ("\r", " ")):
        text = text.replace(source, replacement)
    return text


def published_releases(item):
    """Yield all verified releases, newest first."""
    for release in sorted(item["releases"], key=lambda record: record["publishedAt"], reverse=True):
        if item["tags"].get(release["immutableTag"]) != release["digest"]:
            continue
        yield release


def gh_image_versions_data(name):
    """Return structured, verified releases and their current tags for the template."""
    repository = name if "/" in name else f"tuxcrate/{name}"
    if not re.fullmatch(r"[a-z0-9][a-z0-9_.-]*/[a-z0-9][a-z0-9_.-]*", repository):
        raise ValueError("Expected a lowercase repository name or owner/name")
    fixture = os.environ.get("GH_IMAGE_VERSIONS_FIXTURE")
    if fixture:
        snapshot = json.loads(Path(fixture).read_text())
        item = next(item for item in snapshot["images"] if item["repository"] == repository)
    else:
        item = collect(repository)
    releases = []
    for release in published_releases(item):
        aliases = sorted(
            (tag for tag, digest in item["tags"].items()
             if digest == release["digest"] and tag != release["immutableTag"]),
            key=lambda tag: (tag != release["version"], tag),
        )
        releases.append({**release, "tags": [release["immutableTag"], *aliases]})
    return {
        "image": item["image"],
        "releases": releases,
        "preview": bool(fixture),
    }


def docker_run(arguments):
    """Format shell fragments without changing their quoting or expansions."""
    if (not isinstance(arguments, list) or not arguments
            or not all(isinstance(arg, str) and arg.strip() and "\n" not in arg and "\r" not in arg
                       for arg in arguments)):
        raise ValueError("docker_run must be a nonempty list of single-line shell fragments")
    command = " \\\n  ".join(arguments)
    return f"docker run \\\n  {command}"


def compose_yaml(configuration):
    """Render block-style Compose YAML with a consistent service property order."""
    if not isinstance(configuration, dict) or not isinstance(configuration.get("services"), dict):
        raise ValueError("compose must be a mapping with a services mapping")
    service_keys = (
        "image", "build", "container_name", "hostname", "user", "restart", "init",
        "entrypoint", "command", "working_dir", "environment", "env_file", "ports",
        "expose", "volumes", "devices", "networks", "depends_on", "healthcheck",
    )
    services = {}
    for name, service in configuration["services"].items():
        if isinstance(service, dict):
            ordered = {key: service[key] for key in service_keys if key in service}
            ordered.update((key, value) for key, value in service.items() if key not in ordered)
            services[name] = ordered
        else:
            services[name] = service
    configuration = {**configuration, "services": services}
    return yaml.safe_dump(configuration, sort_keys=False, default_flow_style=False).rstrip()


def define_env(env):
    env.macro(gh_image_versions_data)
    env.filter(cell)
    env.filter(docker_run)
    env.filter(compose_yaml)
