(() => {
  function updateImageTag(code, image, tag) {
    const escapedImage = image.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const references = [...code.textContent.matchAll(
      new RegExp(`${escapedImage}:[A-Za-z0-9_][A-Za-z0-9_.-]*`, "g"),
    )];

    // Work backwards so earlier offsets remain valid. Ranges preserve the
    // surrounding syntax highlighting even when an image spans several tokens.
    for (const reference of references.reverse()) {
      const walker = document.createTreeWalker(code, NodeFilter.SHOW_TEXT);
      const range = document.createRange();
      const start = reference.index;
      const end = start + reference[0].length;
      let offset = 0;
      let node;

      while ((node = walker.nextNode())) {
        const nextOffset = offset + node.textContent.length;
        if (offset <= start && start < nextOffset) {
          range.setStart(node, start - offset);
        }
        if (offset < end && end <= nextOffset) {
          range.setEnd(node, end - offset);
          break;
        }
        offset = nextOffset;
      }

      range.deleteContents();
      range.insertNode(document.createTextNode(`${image}:${tag}`));
    }
  }

  function selectTag(button) {
    const { containerImage: image, containerTag: tag } = button.dataset;
    for (const usage of document.querySelectorAll(".container-usage")) {
      if (usage.dataset.containerImage !== image) continue;
      for (const code of usage.querySelectorAll("pre code")) {
        updateImageTag(code, image, tag);
      }
    }
    for (const candidate of document.querySelectorAll("button[data-container-tag]")) {
      if (candidate.dataset.containerImage === image) {
        candidate.setAttribute("aria-pressed", String(candidate.dataset.containerTag === tag));
      }
    }
  }

  // Delegation also handles pages loaded through client-side navigation.
  document.addEventListener("click", (event) => {
    const more = event.target.closest(".container-versions-more");
    if (more) {
      const list = more.closest(".container-versions");
      const hidden = [...list.querySelectorAll("tbody tr[hidden]")];
      for (const row of hidden.slice(0, Number(list.dataset.loadSize))) {
        row.hidden = false;
      }
      more.hidden = !list.querySelector("tbody tr[hidden]");
      more.closest("tfoot").hidden = more.hidden;
      return;
    }
    const button = event.target.closest("button[data-container-tag]");
    if (button) selectTag(button);
  });

  const initialized = new WeakSet();
  function initialize() {
    for (const list of document.querySelectorAll(".container-versions")) {
      if (initialized.has(list)) continue;
      initialized.add(list);
      const rows = [...list.querySelectorAll("tbody tr")];
      const pageSize = Number(list.dataset.pageSize);
      for (const row of rows.slice(pageSize)) row.hidden = true;
      const more = list.querySelector(".container-versions-more");
      if (more) {
        const footer = list.querySelector("table").createTFoot();
        const cell = footer.insertRow().insertCell();
        cell.colSpan = 4;
        cell.append(more);
        more.hidden = rows.length <= pageSize;
        footer.hidden = more.hidden;
      }
    }
    const images = new Set();
    for (const button of document.querySelectorAll("button[data-container-tag]")) {
      const image = button.dataset.containerImage;
      if (images.has(image)) continue;
      images.add(image);
      if (initialized.has(button)) continue;
      initialized.add(button);
      selectTag(button);
    }
  }

  if (typeof document$ !== "undefined") {
    document$.subscribe(initialize);
  } else if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initialize, { once: true });
  } else {
    initialize();
  }
})();
