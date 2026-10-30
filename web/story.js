// The story page. Vanilla ES module, no build step, like the rest of web/.
//
// The server holds the campaign and plays one scene at a time on a worker
// thread; this polls it. Four endpoints, all hardcoded here the way
// `app.js` hardcodes its nine:
//
//   POST /api/story                start a campaign
//   GET  /api/story/{id}           where it is, and every line so far
//   POST /api/story/{id}/advance   play the next scene
//   POST /api/story/{id}/say       the line the person typed
//
// **Every line carries a `kind`** -- scene, recall, roll, mine, dm, note,
// exit -- and the kind becomes a CSS class. That is the whole reason #930
// existed: who wrote a line governs how much a reader should trust it, and
// the page is where that has to be visible.

const POLL_MS = 700;

const state = {
  id: null,
  shown: 0,      // how many lines are already on the page
  timer: null,
};

const $ = (id) => document.getElementById(id);

// -- settings, beside the fight page's own localStorage keys ---------------

const KEYS = { god: "dnd4e.godmode", scripted: "dnd4e.scripted" };

function readSetting(key) {
  return localStorage.getItem(key) === "1";
}

function writeSetting(key, on) {
  localStorage.setItem(key, on ? "1" : "0");
}

function loadSettings() {
  $("opt-god").checked = readSetting(KEYS.god);
  $("opt-scripted").checked = readSetting(KEYS.scripted);
}

// -- drawing ---------------------------------------------------------------

function addLines(lines) {
  const box = $("transcript");
  for (const line of lines.slice(state.shown)) {
    const el = document.createElement("div");
    // `line-<kind>` is what `style.css` colours and what `browser.py`
    // asserts on. Renaming one is a two-file change.
    el.className = `line line-${line.kind}`;
    el.textContent = line.text;
    box.appendChild(el);
  }
  state.shown = lines.length;
  box.scrollTop = box.scrollHeight;
}

function draw(st) {
  $("module-name").textContent = st.module || "Story";
  $("scene-line").textContent = st.scene_name
    ? `${st.scene_name} (${st.scene_kind})` : "";
  $("party-line").textContent = st.party || "";
  addLines(st.lines || []);

  const asking = Boolean(st.asking);
  $("asking").hidden = !asking;
  $("over").hidden = !st.over;
  // "Continue" only when the server is idle and there is more to play.
  $("advance").hidden = asking || st.over;
  // Thinking: the worker is busy and has not asked anything. Today that is
  // inferred; #931 is about the model reporting its own phase instead.
  $("waiting").hidden = asking || st.over;
  if (asking) $("speech").focus();
}

// -- talking to the server -------------------------------------------------

async function call(path, body) {
  const res = await fetch(path, body
    ? { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body) }
    : { method: "POST" });
  if (!res.ok) throw new Error(`${path}: ${res.status}`);
  return res.json();
}

async function poll() {
  if (!state.id) return;
  const res = await fetch(`/api/story/${state.id}`);
  if (res.ok) draw(await res.json());
}

function watch() {
  if (state.timer) clearInterval(state.timer);
  state.timer = setInterval(poll, POLL_MS);
}

async function start() {
  const body = {
    module: $("opt-module").value.trim(),
    seed: Number($("opt-seed").value) || 0,
    god: $("opt-god").checked,
    scripted: $("opt-scripted").checked,
  };
  writeSetting(KEYS.god, body.god);
  writeSetting(KEYS.scripted, body.scripted);
  const st = await call("/api/story", body);
  state.id = st.id;
  state.shown = 0;
  $("transcript").textContent = "";
  $("settings").hidden = true;
  draw(st);
  await call(`/api/story/${state.id}/advance`);
  watch();
}

async function send() {
  const said = $("speech").value.trim();
  if (!said || !state.id) return;
  $("speech").value = "";
  $("asking").hidden = true;
  draw(await call(`/api/story/${state.id}/say`, { speech: said, doing: "" }));
}

async function advance() {
  if (!state.id) return;
  $("advance").hidden = true;
  draw(await call(`/api/story/${state.id}/advance`));
}

// -- wiring ----------------------------------------------------------------

$("settings-open").addEventListener("click", () => { $("settings").hidden = false; });
$("settings-close").addEventListener("click", () => { $("settings").hidden = true; });
$("start").addEventListener("click", () => { start(); });
$("send").addEventListener("click", () => { send(); });
$("advance").addEventListener("click", () => { advance(); });
$("speech").addEventListener("keydown", (ev) => {
  if (ev.key === "Enter") send();
});

loadSettings();
// Nothing is playing until somebody starts one: a module is the user's own
// file and the server should not open one on a page load.
$("settings").hidden = false;
