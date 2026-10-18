# Container images

These container images package open-source apps ready to run.
Each image page lists published versions and available GHCR tags.

| Image | Description |
| --- | --- |
{% for image in container_pages() -%}
| [{{ image.title | cell }}]({{ image.url }}) | {{ image.description | cell }} |
{% endfor %}
