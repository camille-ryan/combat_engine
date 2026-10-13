// Regex search over the compendium source.
//
// Vanilla ES module, no build step, no dependency -- `web/CLAUDE.md`'s rule,
// and this file is held to it even though it is an instrument rather than the
// page. `node --check scripts/compendium_web/app.js` is its whole cover.
//
// All state lives in the query string, which is how the viewer this copies
// works: back and forward come free, and a search is a link you can keep.

const el = (id) => document.getElementById(id);

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
    button.innerHTML = `${esc(cat.name)}<var>${cat.count.toLocaleString()}</var>`;
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

function repoCell(repo) {
  if (!repo || repo.state === "absent") return "";
  if (repo.state === "unbuilt") return '<span class="unbuilt">(not built)</span>';
  const markers = (repo.markers || []).map((m) => `<span class="marker">${esc(m)}=</span>`);
  return [`<span class="ref">${esc(repo.ref)}</span>`, ...markers].join(" ");
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

    if (row.snippets.length) {
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
  renderCats();
  wire();
  await route();
}

boot().catch((wrong) => fail(`${wrong.message} — is the server still running?`));
