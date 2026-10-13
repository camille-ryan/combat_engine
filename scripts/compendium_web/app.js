// Regex search over the compendium source.
//
// Vanilla ES module, no build step, no dependency -- `web/CLAUDE.md`'s rule,
// and this file is held to it even though it is an instrument rather than the
// page. `node --check scripts/compendium_web/app.js` is its whole cover.
//
// All state lives in the query string, which is how the viewer this copies
// works: back and forward come free, and a search is a link you can keep.

const el = (id) => document.getElementById(id);

// A mark per category, drawn rather than set in a font -- the in-card symbols
// were characters first and the die faces came out as empty boxes at the size
// they render. The viewer this copies uses a licensed pixel-art icon set; these
// are plain geometry, and they only have to make a tab findable at a glance.
const CAT_ICON = {
  Monster: '<path d="M2 13 5 4l3 9 3-9 3 9Z"/>',
  Power: '<path d="M9.5 1 3 9h4l-.5 6L13 7H8.5Z"/>',
  Item: '<path d="M8 1.8 14.2 5v6L8 14.2 1.8 11V5Z"/>',
  Feat: '<path d="M8 1.3 9.95 6.2 15.2 6.5 11.1 9.8 12.5 14.9 8 12.1 3.5 14.9 4.9 9.8.8 6.5 6.05 6.2Z"/>',
  Race: '<circle cx="8" cy="4.2" r="2.7"/><path d="M2.8 14.5c0-3.3 2.3-5.3 5.2-5.3s5.2 2 5.2 5.3Z"/>',
  Class: '<path d="M8 1.4 14 3.8v4.6c0 3.3-2.7 5.5-6 6.2-3.3-.7-6-2.9-6-6.2V3.8Z"/>',
  Trap: '<path d="M1.5 2h13l-2.2 4-2.2-2.6L8 6 6 3.4 3.7 6Zm0 12h13l-2.2-4-2.2 2.6L8 10 6 12.6 3.7 10Z"/>',
  Terrain: '<path d="M1 14 5.5 5.5 8.6 10.5 11 7 15 14Z"/>',
  Disease:
    '<circle cx="8" cy="8" r="6" fill="none" stroke="currentColor" stroke-width="1.6"/>' +
    '<circle cx="6" cy="6.4" r="1.2"/><circle cx="10" cy="7.4" r="1"/><circle cx="7.6" cy="10.4" r="1.1"/>',
  Associate:
    '<circle cx="5.6" cy="8" r="4" fill="none" stroke="currentColor" stroke-width="1.6"/>' +
    '<circle cx="10.4" cy="8" r="4" fill="none" stroke="currentColor" stroke-width="1.6"/>',
  Companion:
    '<ellipse cx="8" cy="10.6" rx="4" ry="3.2"/><circle cx="3.6" cy="6.2" r="1.7"/>' +
    '<circle cx="6.6" cy="4" r="1.8"/><circle cx="9.9" cy="4" r="1.8"/><circle cx="12.6" cy="6.2" r="1.7"/>',
  Background:
    '<path d="M3 2.6h10v10.8H3Z" fill="none" stroke="currentColor" stroke-width="1.5"/>' +
    '<path d="M5.2 5.6h5.6M5.2 8h5.6M5.2 10.4h3.4" fill="none" stroke="currentColor" stroke-width="1.3"/>',
  Deity:
    '<circle cx="8" cy="8" r="3.2"/><path d="M8 .8v2.4M8 12.8v2.4M.8 8h2.4M12.8 8h2.4' +
    'M2.9 2.9 4.6 4.6M11.4 11.4l1.7 1.7M13.1 2.9 11.4 4.6M4.6 11.4 2.9 13.1" ' +
    'fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>',
  EpicDestiny: '<path d="M1.8 13 2.8 4l3.4 3L8 2.6 9.8 7l3.4-3 1 9Z"/>',
  Glossary:
    '<path d="M2.5 2.6h4.6c1 0 1.6.5 1.6 1.3v9.5c0-.7-.6-1.1-1.6-1.1H2.5Z"/>' +
    '<path d="M13.5 2.6H8.9c-1 0-1.6.5-1.6 1.3v9.5c0-.7.6-1.1 1.6-1.1h4.6Z" ' +
    'fill="none" stroke="currentColor" stroke-width="1.4"/>',
  ParagonPath: '<path d="M8 1.5 13.5 7h-3.3v7.5H5.8V7H2.5Z"/>',
  Poison: '<path d="M8 1.5c3 3.6 4.6 6 4.6 8A4.6 4.6 0 0 1 3.4 9.5c0-2 1.6-4.4 4.6-8Z"/>',
  Ritual:
    '<circle cx="8" cy="8" r="6.2" fill="none" stroke="currentColor" stroke-width="1.5"/>' +
    '<path d="M8 3.2 11.8 12 3.2 6.6h9.6L4.2 12Z" fill="none" stroke="currentColor" stroke-width="1.3"/>',
  Skill:
    '<path d="M2.5 8.6 6.3 12.4 13.6 4" fill="none" stroke="currentColor" ' +
    'stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>',
  Theme:
    '<path d="M2 2h6.4l5.6 5.6-6.4 6.4L2 8.4Z" fill="none" stroke="currentColor" stroke-width="1.6"/>' +
    '<circle cx="5.4" cy="5.4" r="1.3"/>',
};

function catIcon(name) {
  const body = CAT_ICON[name] || '<circle cx="8" cy="8" r="4"/>';
  return `<svg class="cat-icon" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">${body}</svg>`;
}

const state = {
  cats: [],
  cat: "",
  q: "",
  targets: new Set(["name", "text"]),
  fold: true,
  filters: {},
  sort: "Name",
  dir: "asc",
  page: 1,
  snippets: false,
  // The last result set, so the card's prev/next walk the search you ran
  // rather than the whole category.
  last: null,
};

// Which category the current <thead> was built for. Rebuilding it on every
// keystroke would take the focus out of the column filter being typed into.
let headFor = "";

function esc(value) {
  if (value === null || value === undefined) return "";
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function debounce(fn, ms) {
  let timer = 0;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), ms);
  };
}

// ------- the URL is the state

function readURL() {
  const q = new URLSearchParams(location.search);
  const view = q.get("view");
  if (view) return { view };

  state.cat = q.get("cat") || state.cats[0]?.name || "Monster";
  state.q = q.get("q") || "";
  const targets = (q.get("in") || "name,text").split(",").filter(Boolean);
  state.targets = new Set(targets);
  state.fold = q.get("fold") !== "0";
  state.sort = q.get("sort") || "Name";
  state.dir = q.get("dir") === "desc" ? "desc" : "asc";
  state.page = Math.max(1, parseInt(q.get("page") || "1", 10) || 1);
  state.snippets = q.get("snip") === "1";
  state.filters = {};
  for (const [key, value] of q) {
    if (key.startsWith("col.") && value) state.filters[key.slice(4)] = value;
  }
  return { view: null };
}

function listQuery() {
  const q = new URLSearchParams();
  q.set("cat", state.cat);
  if (state.q) q.set("q", state.q);
  q.set("in", [...state.targets].join(","));
  if (!state.fold) q.set("fold", "0");
  if (state.sort !== "Name") q.set("sort", state.sort);
  if (state.dir !== "asc") q.set("dir", state.dir);
  if (state.page !== 1) q.set("page", String(state.page));
  if (state.snippets) q.set("snip", "1");
  for (const [name, expr] of Object.entries(state.filters)) {
    if (expr) q.set(`col.${name}`, expr);
  }
  return q;
}

function go(query, push) {
  const url = `${location.pathname}?${query}`;
  if (push) history.pushState(null, "", url);
  else history.replaceState(null, "", url);
}

// ------- fetching

async function getJSON(url) {
  const res = await fetch(url);
  const body = await res.json().catch(() => ({ error: `${res.status} ${res.statusText}` }));
  if (!res.ok) throw new Error(body.error || `${res.status} ${res.statusText}`);
  return body;
}

function fail(message) {
  const box = el("error");
  box.textContent = message;
  box.hidden = !message;
}

// ------- the list

function renderCats() {
  const box = el("cats");
  box.innerHTML = "";
  for (const cat of state.cats) {
    const button = document.createElement("button");
    button.type = "button";
    button.dataset.cat = cat.name;
    button.setAttribute("role", "tab");
    button.setAttribute("aria-selected", String(cat.name === state.cat));
    button.innerHTML =
      `${catIcon(cat.name)}<b>${esc(cat.name)}</b>` +
      `<var data-cat="${esc(cat.name)}">${cat.count.toLocaleString()}</var>`;
    button.addEventListener("click", () => {
      if (state.cat === cat.name) return;
      state.cat = cat.name;
      state.page = 1;
      state.sort = "Name";
      state.dir = "asc";
      state.filters = {};
      go(listQuery(), true);
      search();
    });
    box.appendChild(button);
  }
}

function markCats() {
  for (const button of el("cats").querySelectorAll("button")) {
    button.setAttribute("aria-selected", String(button.dataset.cat === state.cat));
  }
}

function renderHead(data) {
  const table = el("results");
  const head = table.querySelector("thead");
  head.innerHTML = "";
  const row = document.createElement("tr");
  const cross = state.cats.find((c) => c.name === data.category)?.cross;
  const headings = [...data.columns, ...(cross ? ["repo"] : [])];

  for (const name of headings) {
    const th = document.createElement("th");
    if (name === "repo") {
      th.textContent = "repo";
      row.appendChild(th);
      continue;
    }
    const sort = document.createElement("button");
    sort.type = "button";
    sort.className = "sort";
    sort.dataset.column = name;
    sort.textContent = name;
    sort.addEventListener("click", () => {
      if (state.sort === name) state.dir = state.dir === "asc" ? "desc" : "asc";
      else {
        state.sort = name;
        state.dir = "asc";
      }
      state.page = 1;
      go(listQuery(), true);
      search();
    });
    th.appendChild(sort);

    const filter = document.createElement("input");
    filter.type = "search";
    filter.placeholder = "regex";
    filter.value = state.filters[name] || "";
    filter.dataset.column = name;
    filter.addEventListener("input", onFilter);
    th.appendChild(filter);
    row.appendChild(th);
  }
  head.appendChild(row);
  headFor = data.category;
}

const onFilter = debounce((event) => {
  const name = event.target.dataset.column;
  const value = event.target.value.trim();
  if (value) state.filters[name] = value;
  else delete state.filters[name];
  state.page = 1;
  go(listQuery(), false);
  search();
}, 250);

function markSort() {
  for (const button of el("results").querySelectorAll("button.sort")) {
    const active = button.dataset.column === state.sort;
    const arrow = state.dir === "asc" ? " ▲" : " ▼";
    button.textContent = button.dataset.column + (active ? arrow : "");
  }
}

// A marker with no value is the marker minus the only thing anyone wants from
// it. `dropped=` alone says a row is unfinished; `dropped= c.shift(path=)` says
// what it is unfinished *on*. The first value shows, the rest are a +N with the
// whole list on hover.
function markerChips(markers) {
  return Object.entries(markers || {}).map(([name, values]) => {
    // A flag marker has no value, so it gets no `=` either. Writing one and
    // leaving it empty is the thing being fixed here, not a shape to keep.
    if (!values.length) return `<span class="marker"><b>${esc(name)}</b></span>`;
    const more = values.length > 1 ? ` +${values.length - 1}` : "";
    return (
      `<span class="marker" title="${esc(`${name}= ${values.join(", ")}`)}">` +
      `<b>${esc(name)}=</b> ${esc(values[0])}${more}</span>`
    );
  });
}

function repoCell(repo) {
  if (!repo || repo.state === "absent") return "";
  if (repo.state === "unbuilt") return '<span class="unbuilt">(not built)</span>';
  return [`<span class="ref">${esc(repo.ref)}</span>`, ...markerChips(repo.markers)].join(" ");
}

function renderBody(data) {
  const body = el("results").querySelector("tbody");
  body.innerHTML = "";
  const cross = state.cats.find((c) => c.name === data.category)?.cross;
  const width = data.columns.length + (cross ? 1 : 0);

  for (const row of data.rows) {
    const tr = document.createElement("tr");
    tr.dataset.id = String(row.id);
    tr.className = "hit";
    const cells = data.columns.map((name) => {
      const value = row.cells[name];
      const numeric = typeof value === "number";
      return `<td class="${numeric ? "num" : ""}">${esc(value)}</td>`;
    });
    if (cross) cells.push(`<td>${repoCell(row.repo)}</td>`);
    tr.innerHTML = cells.join("");
    tr.addEventListener("click", () => open(data.category, row.id));
    body.appendChild(tr);

    // Off by default: a line of card prose under every row is clutter in a
    // list you are scanning. The checkbox brings it back when the question is
    // "what in the text matched".
    if (state.snippets && row.snippets.length) {
      const snip = document.createElement("tr");
      snip.className = "snip";
      // The snippets arrive escaped, with the match already wrapped in a
      // <mark>, so this is the one place markup from the server is trusted.
      snip.innerHTML =
        `<td colspan="${width}">` + row.snippets.map((s) => `<p>${s}</p>`).join("") + "</td>";
      body.appendChild(snip);
    }
  }

  el("empty").hidden = data.rows.length > 0;
}

function renderCaption(data) {
  const matched = data.matched.toLocaleString();
  const all = data.total.toLocaleString();
  el("showing").textContent =
    data.matched === data.total ? `${all} rows` : `${matched} of ${all} rows`;
  el("pages").textContent = data.pages > 1 ? `page ${data.page} of ${data.pages}` : "";
  el("list_prev").disabled = data.page <= 1;
  el("list_next").disabled = data.page >= data.pages;
}

// Every tab's count, for the pattern now in the box. Without it a tab reads
// 9,409 whatever you typed and the only way to find out whether the pattern
// has anything in that category is to click it.
let countsToken = 0;
let countsKey = "";

function catCounts() {
  const q = new URLSearchParams();
  if (state.q) q.set("q", state.q);
  q.set("in", [...state.targets].join(","));
  if (!state.fold) q.set("fold", "0");
  return q;
}

function setCount(node, n) {
  node.textContent = n === undefined || n === null ? "–" : n.toLocaleString();
  node.classList.toggle("none", n === 0);
  node.classList.remove("pending");
}

async function updateCounts(matchedHere) {
  const vars = [...el("cats").querySelectorAll("var")];
  const here = vars.find((v) => v.dataset.cat === state.cat);
  // The open tab always takes the search's own number, so it cannot disagree
  // with the caption under it when a column filter is narrowing the rows.
  if (here) setCount(here, matchedHere);

  const key = catCounts().toString();
  if (key === countsKey) return; // same pattern, different tab: nothing moved
  const mine = ++countsToken;
  for (const v of vars) if (v !== here) v.classList.add("pending");
  try {
    const data = await getJSON(`/api/counts?${key}`);
    if (mine !== countsToken) return; // a later search overtook this one
    countsKey = key;
    for (const v of vars) {
      if (v.dataset.cat === state.cat) setCount(v, matchedHere);
      else setCount(v, data.counts[v.dataset.cat]);
    }
  } catch {
    for (const v of vars) v.classList.remove("pending");
  }
}

async function search() {
  markCats();
  try {
    const data = await getJSON(`/api/search?${listQuery()}`);
    fail("");
    state.last = data;
    state.page = data.page;
    if (data.category !== headFor) renderHead(data);
    markSort();
    renderBody(data);
    renderCaption(data);
    updateCounts(data.matched);
  } catch (wrong) {
    // A pattern that does not compile must read as a typo. The rows stay as
    // they were -- blanking them would be the one lie this tool exists to
    // avoid, a broken pattern looking like a true negative.
    fail(wrong.message);
  }
}

// ------- one card

function open(cat, id) {
  go(new URLSearchParams({ view: `${cat}.${id}` }), true);
  showCard(cat, id);
}

async function showCard(cat, id) {
  show("view");
  el("card").innerHTML = "<p>…</p>";
  try {
    const data = await getJSON(`/api/entry?cat=${encodeURIComponent(cat)}&id=${id}`);
    el("card").innerHTML = data.html;
    el("view_repo").innerHTML = repoCell(data.repo);
    el("banner").textContent = `${cat} ${id}`;
    const where = neighbours(cat, id);
    el("view_prev").disabled = where.prev === null;
    el("view_next").disabled = where.next === null;
  } catch (wrong) {
    el("card").innerHTML = `<p class="warn">${esc(wrong.message)}</p>`;
  }
}

function neighbours(cat, id) {
  const rows = state.last && state.last.category === cat ? state.last.rows : [];
  const at = rows.findIndex((r) => r.id === id);
  if (at < 0) return { prev: null, next: null };
  return {
    prev: at > 0 ? rows[at - 1].id : null,
    next: at < rows.length - 1 ? rows[at + 1].id : null,
  };
}

function step(delta) {
  const q = new URLSearchParams(location.search).get("view");
  if (!q) return;
  const [cat, id] = [q.slice(0, q.lastIndexOf(".")), Number(q.slice(q.lastIndexOf(".") + 1))];
  const where = neighbours(cat, id);
  const to = delta < 0 ? where.prev : where.next;
  if (to !== null) open(cat, to);
}

// ------- which screen

function show(which) {
  for (const name of ["list", "view", "about"]) el(name).hidden = name !== which;
  if (which === "list") el("banner").textContent = "compendium";
  if (which === "about") el("banner").textContent = "about";
  window.scroll(0, 0);
}

function backToList() {
  go(listQuery(), true);
  show("list");
  search();
}

async function route() {
  const { view } = readURL();
  if (view) {
    const at = view.lastIndexOf(".");
    showCard(view.slice(0, at), Number(view.slice(at + 1)));
    return;
  }
  show("list");
  // Put the controls back in step with the URL that was just read.
  el("q").value = state.q;
  el("fold").checked = state.fold;
  el("snippets").checked = state.snippets;
  for (const button of el("targets").querySelectorAll("button.pressable")) {
    button.setAttribute("aria-pressed", String(state.targets.has(button.dataset.target)));
  }
  if (state.cat !== headFor) headFor = "";
  await search();
}

// ------- wiring

function wire() {
  const typed = debounce(() => {
    state.q = el("q").value;
    state.page = 1;
    go(listQuery(), false);
    search();
  }, 250);
  el("q").addEventListener("input", typed);
  el("q").addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      state.q = el("q").value;
      state.page = 1;
      go(listQuery(), true);
      search();
    }
  });

  for (const button of el("targets").querySelectorAll("button.pressable")) {
    button.addEventListener("click", () => {
      const name = button.dataset.target;
      if (state.targets.has(name)) state.targets.delete(name);
      else state.targets.add(name);
      // Every target off would match nothing for any pattern, which looks like
      // a result rather than a mistake. Keep the one just clicked.
      if (state.targets.size === 0) state.targets.add(name);
      for (const other of el("targets").querySelectorAll("button.pressable")) {
        other.setAttribute("aria-pressed", String(state.targets.has(other.dataset.target)));
      }
      state.page = 1;
      go(listQuery(), false);
      search();
    });
  }

  el("btn_clear").addEventListener("click", () => {
    state.q = "";
    state.filters = {};
    state.page = 1;
    el("q").value = "";
    headFor = "";
    go(listQuery(), true);
    search();
    el("q").focus();
  });

  el("fold").addEventListener("change", () => {
    state.fold = el("fold").checked;
    state.page = 1;
    go(listQuery(), false);
    search();
  });

  el("highlight").addEventListener("change", () => {
    document.body.classList.toggle("no_highlight", !el("highlight").checked);
  });

  el("snippets").addEventListener("change", () => {
    state.snippets = el("snippets").checked;
    go(listQuery(), false);
    if (state.last) renderBody(state.last); // already fetched; no round trip
  });

  el("list_prev").addEventListener("click", () => flip(-1));
  el("list_next").addEventListener("click", () => flip(1));
  el("view_prev").addEventListener("click", () => step(-1));
  el("view_next").addEventListener("click", () => step(1));

  el("btn_back").addEventListener("click", backToList);
  el("btn_about_back").addEventListener("click", backToList);
  el("btn_about").addEventListener("click", () => show("about"));

  document.addEventListener("keydown", (event) => {
    if (event.target.tagName === "INPUT") return;
    if (event.key === "Escape" && el("list").hidden) backToList();
    if (event.key === "ArrowLeft") el("list").hidden ? step(-1) : flip(-1);
    if (event.key === "ArrowRight") el("list").hidden ? step(1) : flip(1);
  });

  // The card's internal cross-references are plain `?view=` links; let them
  // route rather than reload.
  el("card").addEventListener("click", (event) => {
    const link = event.target.closest("a[href^='?view=']");
    if (!link) return;
    event.preventDefault();
    const view = new URLSearchParams(link.getAttribute("href").slice(1)).get("view");
    const at = view.lastIndexOf(".");
    open(view.slice(0, at), Number(view.slice(at + 1)));
  });

  window.addEventListener("popstate", route);
}

function flip(delta) {
  if (!state.last) return;
  const to = state.last.page + delta;
  if (to < 1 || to > state.last.pages) return;
  state.page = to;
  go(listQuery(), false);
  search();
}

async function boot() {
  const table = el("results");
  if (!table) return;
  const catalogue = await getJSON("/api/categories");
  state.cats = catalogue.categories;
  el("nobuild").hidden = catalogue.built;
  // The marker list in compendium.py is a hand-kept copy of a set the DSL
  // does not export. If the DSL grows a parameter this page has never heard
  // of, say so here rather than quietly reporting a row as unmarked.
  const drifted = catalogue.unclassified || [];
  el("drift").hidden = drifted.length === 0;
  el("drift").textContent =
    `dsl.power() has ${drifted.length} unclassified parameter(s): ${drifted.join(", ")}` +
    " — a marker among them would not show in the repo column.";
  renderCats();
  wire();
  await route();
}

boot().catch((wrong) => fail(`${wrong.message} — is the server still running?`));
