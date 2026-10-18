const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const { join } = require("node:path");
const { test } = require("node:test");
const { runInNewContext } = require("node:vm");

function versionList(count) {
  const rows = Array.from({ length: count }, () => ({ hidden: false }));
  const cell = { append: (button) => { cell.button = button; } };
  const footer = { insertRow: () => ({ insertCell: () => cell }) };
  const table = { createTFoot: () => footer };
  const more = count > 3 ? {
    hidden: true,
    closest: (selector) => selector === "tfoot" ? footer : list,
  } : null;
  const list = {
    dataset: { pageSize: "3", loadSize: "5" },
    rows,
    more,
    footer,
    cell,
    querySelectorAll: (selector) => selector === "tbody tr" ? rows : rows.filter((row) => row.hidden),
    querySelector: (selector) => {
      if (selector === ".container-versions-more") return more;
      if (selector === "table") return table;
      return rows.find((row) => row.hidden);
    },
  };
  return list;
}

function setup(lists) {
  let click;
  let initialize;
  runInNewContext(readFileSync(join(__dirname, "../../docs/javascripts/container-tags.js"), "utf8"), {
    document: {
      querySelectorAll: (selector) => selector === ".container-versions" ? lists : [],
      addEventListener: (event, listener) => {
        if (event === "click") click = listener;
      },
    },
    document$: { subscribe: (listener) => { initialize = listener; } },
  });
  initialize();
  return {
    initialize,
    clickMore: (list) => click({
      target: { closest: (selector) => selector === ".container-versions-more" ? list.more : null },
    }),
  };
}

test("shows three releases and reveals five more per click until exhausted", () => {
  const list = versionList(14);
  const page = setup([list]);
  const visible = () => list.rows.filter((row) => !row.hidden).length;
  assert.equal(visible(), 3);
  assert.equal(list.more.hidden, false);
  assert.equal(list.cell.colSpan, 4);
  assert.equal(list.cell.button, list.more);
  assert.equal(list.footer.hidden, false);
  page.clickMore(list);
  assert.equal(visible(), 8);
  assert.equal(list.more.hidden, false);
  page.clickMore(list);
  assert.equal(visible(), 13);
  assert.equal(list.more.hidden, false);
  assert.equal(list.footer.hidden, false);
  page.clickMore(list);
  assert.equal(visible(), 14);
  assert.equal(list.more.hidden, true);
  assert.equal(list.footer.hidden, true);
  page.initialize();
  assert.equal(visible(), 14);
});

test("handles short lists and initializes newly navigated pages independently", () => {
  const lists = [versionList(0), versionList(2), versionList(3), versionList(4)];
  const page = setup(lists);
  for (const list of lists.slice(0, 3)) {
    assert.ok(list.rows.every((row) => !row.hidden));
    assert.equal(list.more, null);
  }
  page.clickMore(lists[3]);
  assert.equal(lists[3].more.hidden, true);
  const next = versionList(7);
  lists.push(next);
  page.initialize();
  assert.equal(next.rows.filter((row) => !row.hidden).length, 3);
  assert.equal(next.more.hidden, false);
  assert.equal(lists[3].more.hidden, true);
});

test("paginates track tables independently", () => {
  const stable = versionList(9);
  const preview = versionList(4);
  const page = setup([stable, preview]);
  page.clickMore(stable);
  assert.equal(stable.rows.filter((row) => !row.hidden).length, 8);
  assert.equal(preview.rows.filter((row) => !row.hidden).length, 3);
  assert.equal(preview.more.hidden, false);
  page.clickMore(preview);
  assert.equal(preview.rows.filter((row) => !row.hidden).length, 4);
  assert.equal(preview.more.hidden, true);
  assert.equal(stable.more.hidden, false);
});
