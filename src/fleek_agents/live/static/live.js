// The live demo: onboarding, then the buyer's and the seller's screens side by side.
// Everything shown comes from the server; this file only lays it out. Text typed by people
// (descriptions, notes) is always set with textContent, never as HTML.
"use strict";

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const GRADES = ["A", "B", "C", "AB", "BC", "ABC"];

let options = null;
let step = 1;
let lotCount = 0;
let playing = false;
let last = null;
let showFiltered = false;

async function api(path, body) {
  const res = await fetch(path, body === undefined ? {} : {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || "Something went wrong.");
  return data;
}

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null) continue;
    if (k === "class") node.className = v;
    else if (k === "text") node.textContent = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v);
  }
  for (const c of children) if (c) node.append(c);
  return node;
}

const pounds = (p) => (p == null ? "" : (p / 100).toFixed(2));
const pence = (v) => (v === "" || v == null ? null : Math.round(parseFloat(v) * 100));
const int = (v) => (v === "" || v == null ? null : parseInt(v, 10));

// ---------- Onboarding ----------

function addLot(values = {}) {
  lotCount += 1;
  const n = lotCount;
  const node = $("#lot-template").content.firstElementChild.cloneNode(true);
  $("[data-n]", node).textContent = n;
  $$('input[type="radio"]', node).forEach((r) => (r.name = `mode_${n}`));
  const firm = $(".firm", node);
  $$('input[type="radio"]', node).forEach((r) =>
    r.addEventListener("change", () => (firm.hidden = r.value !== "firm" || !r.checked)));
  $(".remove", node).addEventListener("click", (event) => {
    event.preventDefault(); // the button sits in the summary: don't fold the lot as well
    if ($$(".lot-form").length > 1) node.remove();
  });
  $("#stock").append(node);
  fillLot(node, values);
  const summary = () => {
    const title = $('[name="title"]', node).value || `Lot ${n}`;
    const price = $('[name="list_price"]', node).value;
    const mode = $$('input[type="radio"]', node).find((r) => r.checked).value;
    $(".lot-summary", node).textContent =
      `${title}${price ? ` · £${price} a piece` : ""}${mode === "firm" ? " · firm price" : ""}`;
  };
  node.addEventListener("input", summary);
  node.addEventListener("change", summary);
  summary();
  node.open = !values.title; // a new, empty lot opens; ready-made ones stay folded
}

function fillLot(node, v) {
  const set = (name, value) => { const f = $(`[name="${name}"]`, node); if (f && value != null) f.value = value; };
  set("title", v.title); set("brand", v.brand); set("category", v.category);
  set("grade", v.grade || "A"); set("pieces", v.pieces); set("bundles", v.bundles);
  set("list_price", pounds(v.list_price)); set("shipping", pounds(v.shipping));
  set("description", v.description); set("floor", pounds(v.floor));
  set("firm_price", pounds(v.firm_price)); set("sell_by", v.sell_by);
  set("walkaway_offer_pct", v.walkaway_offer_pct);
  const mode = v.mode || "haggle";
  $$('input[type="radio"]', node).forEach((r) => (r.checked = r.value === mode));
  $(".firm", node).hidden = mode !== "firm";
}

function fillBuyer(b) {
  const f = $("#form");
  f.buyer_name.value = b.name; f.buyer_kind.value = b.kind; f.buyer_country.value = b.country;
  f.buyer_category.value = b.category; f.buyer_brands.value = (b.brands || []).join(", ");
  f.buyer_pieces.value = b.pieces; f.buyer_notes.value = b.notes || "";
  f.buyer_top.value = pounds(b.top_price);
  $$('[name="grade_ok"]').forEach((c) => (c.checked = b.grades.includes(c.value)));
  $$('[name="buyer_final_say"]').forEach((r) => (r.checked = r.value === b.final_say));
}

function fill(preset) {
  const f = $("#form");
  f.seller_name.value = preset.seller.name;
  f.seller_country.value = preset.seller.country || "PK";
  $$('[name="seller_final_say"]').forEach((r) => (r.checked = r.value === preset.seller.final_say));
  $("#stock").replaceChildren();
  lotCount = 0;
  preset.seller.stock.forEach((lot) => addLot(lot));
  fillBuyer(preset.buyer);
  $("#buyer-pick").value = "0";
}

function collect() {
  const f = $("#form");
  const stock = $$(".lot-form").map((node) => {
    const v = (name) => $(`[name="${name}"]`, node).value.trim();
    const mode = $$('input[type="radio"]', node).find((r) => r.checked).value;
    const line = {
      title: v("title"), brand: v("brand"), category: v("category"), grade: v("grade"),
      pieces: int(v("pieces")), bundles: int(v("bundles")), list_price: pence(v("list_price")),
      shipping: pence(v("shipping")), description: v("description"), floor: pence(v("floor")), mode,
    };
    if (mode === "firm") line.firm_price = pence(v("firm_price"));
    if (v("sell_by")) line.sell_by = v("sell_by");
    if (v("walkaway_offer_pct")) line.walkaway_offer_pct = int(v("walkaway_offer_pct"));
    return line;
  });
  return {
    seller: {
      name: f.seller_name.value.trim(), country: f.seller_country.value.trim().toUpperCase(),
      final_say: $('[name="seller_final_say"]:checked').value, stock,
    },
    buyer: {
      name: f.buyer_name.value.trim(), kind: f.buyer_kind.value,
      country: f.buyer_country.value.trim().toUpperCase(),
      category: f.buyer_category.value.trim(),
      brands: f.buyer_brands.value.split(",").map((s) => s.trim()).filter(Boolean),
      grades: $$('[name="grade_ok"]:checked').map((c) => c.value),
      pieces: int(f.buyer_pieces.value), notes: f.buyer_notes.value.trim(),
      top_price: pence(f.buyer_top.value), final_say: $('[name="buyer_final_say"]:checked').value,
    },
    agents: $('[name="agents"]:checked').value,
    others: options.preset.others,
  };
}

function showStep(n) {
  step = n;
  $$("fieldset.step").forEach((fs) => (fs.hidden = Number(fs.dataset.step) !== n));
  $$(".steps li").forEach((li) => li.classList.toggle("on", Number(li.dataset.step) === n));
  $("#back").hidden = n === 1;
  $("#next").hidden = n === 3;
  $("#start").hidden = n !== 3;
  $("#form-error").hidden = true;
}

function stepValid() {
  const fs = $(`fieldset.step[data-step="${step}"]`);
  for (const input of $$("input[required], select[required]", fs)) {
    if (!input.closest("[hidden]") && !input.value.trim()) {
      showError(`Fill in: ${input.closest("label").firstChild.textContent.trim()}`);
      const lot = input.closest("details");
      if (lot) lot.open = true;
      input.focus();
      return false;
    }
  }
  if (step === 2 && !$$('[name="grade_ok"]:checked').length) {
    showError("Pick at least one grade.");
    return false;
  }
  return true;
}

function showError(text) {
  const box = $("#form-error");
  box.textContent = text;
  box.hidden = false;
}

// ---------- The two screens ----------

const TURN = { open: "ralph", countered: "ralph", offered: "tommy" };

function lotBox(view, side) {
  const lot = view.lot;
  if (!lot) return [el("p", { class: "muted", text: "No lot matched, so no agent was called." })];
  const facts = el("div", { class: "facts" },
    el("span", { text: `Grade ${lot.grade}` }),
    el("span", { text: `${lot.bundles} × ${lot.pieces} pieces` }),
    el("span", { text: `List ${view.list_price_for_order} a piece` }),
    el("span", { text: `Shipping ${lot.shipping}` }));
  const mode = lot.mode === "firm"
    ? el("span", { class: "pill firm", text: `Firm price ${lot.firm_price}` })
    : el("span", { class: "pill", text: "Haggle" });
  const extras = [];
  if (lot.sell_by) extras.push(el("span", { class: "pill", text: `Sell by ${lot.sell_by}` }));
  if (lot.walkaway_offer_pct) extras.push(el("span", { class: "pill", text: `${lot.walkaway_offer_pct}% off if you walk away` }));
  const parts = [el("b", { text: lot.title }), facts, el("div", { class: "facts" }, mode, ...extras)];
  if (side === "buyer") {
    parts.push(el("div", { class: "note" },
      el("span", { class: "muted small", text: "Ralph doesn't read the seller's words. You can: " }),
      el("span", { text: view.buyer.description || "(no description)" })));
  } else {
    parts.push(el("div", { class: "note" },
      el("span", { class: "muted small", text: "Your description (Tommy reads it): " }),
      el("span", { text: view.buyer.description || "(none)" })));
  }
  return parts;
}

function lineItem(line, mine) {
  const at = el("span", { class: "at", text: `${line.at}` });
  const cls = {
    card: `card ${line.who}${line.who === mine ? " mine" : ""}`,
    check: "check",
    stop: "stop", ask: "ask", end: "end", note: "note",
  }[line.kind] || "note";
  return el("li", { class: cls }, at, document.createTextNode(line.text));
}

function renderScreen(root, data, view, side) {
  const agent = side === "buyer" ? "ralph" : "tommy";
  $('[data-field="name"]', root).textContent = data.name;
  const what = side === "buyer" ? "Your top price" : "Your floor for this lot";
  $('[data-field="secret"]', root).textContent = data.secret
    ? `🔒 ${what}: ${data.secret}. Only you and the vault see this.` : "";
  $('[data-field="lot"]', root).replaceChildren(...lotBox(view, side));
  const list = $('[data-field="lines"]', root);
  list.replaceChildren(...data.lines.map((l) => lineItem(l, agent)));
  list.scrollTop = list.scrollHeight;
  const ask = $('[data-field="ask"]', root);
  ask.hidden = !data.asked;
  if (data.asked) {
    ask.replaceChildren(
      el("p", { text: "The agents agreed. Your OK closes the deal." }),
      el("button", { class: "ok", text: "Approve", onclick: () => decide(side, "approve") }),
      el("button", { class: "bad", text: "Reject", onclick: () => decide(side, "reject") }));
  }
  const controls = $(`.controls[data-side="${side}"]`);
  const live = !view.over && !view.waiting;
  controls.replaceChildren(
    el("button", {
      text: view.paused ? "Resume" : "Pause", disabled: live ? null : "",
      onclick: () => control(view.paused ? "resume" : "pause", side),
    }),
    el("button", { text: "Hand to an account manager", onclick: () => control("hand_over", side) }),
    el("button", { class: "bad", text: "Stop", onclick: () => control("stop", side) }));
  $$("button", controls).forEach((b) => { if (!live) b.disabled = true; });
}

function renderFunnel(root, view) {
  const fu = view.fleek.funnel;
  if (!fu || !fu.rows) return;
  const ranked = fu.rows.filter((r) => r.step === "ranked").length;
  $('[data-field="funnel-steps"]', root).replaceChildren(
    el("li", { text: `${fu.lots} lots from ${fu.sellers} sellers` }),
    el("li", { text: `${fu.passed} pass the filters` }),
    el("li", { text: `${fu.possible} the vault says a price can work` }),
    el("li", { text: `${ranked} ranked` }));
  const current = view.lot ? view.lot.id : null;
  const filtered = fu.rows.filter((r) => r.step === "filters").length;
  const toggle = el("tr", { class: "toggle" }, el("td", { colspan: "4" },
    el("button", {
      class: "link", type: "button",
      text: showFiltered ? `Hide the ${filtered} lots the filters dropped` : `Show the ${filtered} lots the filters dropped`,
      onclick: () => { showFiltered = !showFiltered; renderFunnel(root, view); },
    })));
  const rows = fu.rows.filter((r) => r.step !== "filters" || showFiltered);
  $('[data-field="funnel-rows"]', root).replaceChildren(...rows.map((r) => {
    let result, why;
    if (r.step === "ranked") {
      result = `#${r.rank}`;
      why = `score ${r.total} = fit ${r.fit}, price ${r.price} (${r.delivered} delivered), rating ${r.quality}/5, dispatch ${r.dispatch_days} days`;
    } else if (r.step === "vault") {
      result = "no price"; why = r.why;
    } else {
      result = "filtered"; why = r.why;
    }
    const row = el("tr", { class: `${r.step}${r.lot === current ? " current" : ""}` },
      el("td", { text: r.lot === current ? `${result} ◀ now` : result }),
      el("td", { text: r.title }), el("td", { text: r.seller }), el("td", { text: why }));
    return row;
  }), ...(filtered ? [toggle] : []));
  const w = fu.weights;
  $('[data-field="weights"]', root).textContent =
    `Ranking uses public facts only, weighted fit ${w.fit}, price ${w.price}, seller rating ${w.quality}, dispatch ${w.speed} (market.toml). The vault's yes or no is the only part that touches a secret, and it never gives a number.`;
}

function renderMetrics(root, m) {
  const t = m.totals;
  const pairs = [
    ["Agent turns", t.agent_turns], ["Model calls", t.model_calls],
    ["Tokens in / out", `${t.tokens_in} / ${t.tokens_out}`], ["AI cost", `${t.cost_cents}¢`],
    ["Agent time", `${t.wall_seconds}s`], ["Lots tried", t.lots_tried], ["Cards", t.cards],
    ["Simulated time", `${t.simulated_hours}h`], ["Deal price", t.price_vs_list || "–"],
    ["Vault stops", t.vault_stops],
  ];
  $('[data-field="metrics"]', root).replaceChildren(...pairs.flatMap(([k, v]) =>
    [el("dt", { text: k }), el("dd", { text: String(v) })]));
}

function render(view) {
  last = view;
  $("#agents-label").textContent = view.agents;
  $("#clock").hidden = false;
  $("#clock").textContent = view.time;
  renderScreen($("#buyer-screen"), view.buyer, view, "buyer");
  renderScreen($("#seller-screen"), view.seller, view, "seller");
  const f = $("#fleek-screen");
  renderFunnel(f, view);
  renderMetrics(f, view.fleek.metrics);
  $('[data-field="lines"]', f).replaceChildren(...view.fleek.lines.map((l) => lineItem(l, "")));
  $('[data-field="watch"]', f).replaceChildren(...(view.fleek.watch.length
    ? view.fleek.watch.map((w) => el("li", { text: `${w.buyer}: ${w.why}` }))
    : [el("li", { class: "muted", text: "Nobody flagged." })]));
  const ask = $('[data-field="ask"]', f);
  ask.hidden = !view.fleek.asked;
  if (view.fleek.asked) {
    ask.replaceChildren(
      el("p", { text: "An account manager's OK is needed." }),
      el("button", { class: "ok", text: "Approve", onclick: () => decide("account_manager", "approve") }),
      el("button", { class: "bad", text: "Reject", onclick: () => decide("account_manager", "reject") }));
  }
  status(view);
}

function status(view, thinking = false) {
  const box = $("#status");
  box.classList.toggle("thinking", thinking);
  let text;
  if (view.state === "no_match") text = "No match.";
  else if (view.over) text = `Over: ${view.state.replaceAll("_", " ")}.`;
  else if (view.waiting) text = "Agreed. Waiting for a person's OK.";
  else if (view.paused) text = "Paused.";
  else if (thinking) text = `${TURN[view.state] === "ralph" ? "Ralph" : "Tommy"} is thinking`;
  else text = `${TURN[view.state] === "ralph" ? "Ralph" : "Tommy"}'s turn.`;
  box.textContent = text;
  const done = view.over || view.waiting || view.paused || view.state === "no_match";
  $("#play").disabled = done;
  $("#step").disabled = done || playing;
  if (done) setPlaying(false);
}

function setPlaying(on) {
  playing = on;
  $("#play").textContent = on ? "❚❚ Hold" : "▶ Run";
}

async function oneTurn() {
  status(last, true);
  try {
    render(await api("/api/step", {}));
  } catch (error) {
    setPlaying(false);
    $("#status").textContent = error.message;
  }
}

async function run() {
  while (playing && last && !last.over && !last.waiting && !last.paused) {
    await oneTurn();
    await new Promise((r) => setTimeout(r, 650));
  }
}

async function control(action, side) {
  try { render(await api("/api/control", { action, side })); } catch (e) { $("#status").textContent = e.message; }
}

async function decide(who, decision) {
  try { render(await api("/api/decide", { who, decision })); } catch (e) { $("#status").textContent = e.message; }
}

// ---------- Wiring ----------

async function init() {
  options = await api("/api/options");
  const grades = $("#grades");
  GRADES.forEach((g) => grades.append(el("label", {},
    el("input", { type: "checkbox", name: "grade_ok", value: g }), document.createTextNode(` ${g}`))));
  const choice = $("#agent-choice");
  options.agents.forEach((a, i) => choice.append(el("label", {},
    el("input", { type: "radio", name: "agents", value: a.key, ...(i === 0 ? { checked: "" } : {}) }),
    document.createTextNode(` ${a.label}`))));
  const pick = $("#buyer-pick");
  options.buyers.forEach((b, i) => pick.append(el("option", { value: String(i), text: `${b.name}: ${b.category}` })));
  pick.append(el("option", { value: "own", text: "My own (type below)" }));
  pick.addEventListener("change", () => { if (pick.value !== "own") fillBuyer(options.buyers[Number(pick.value)]); });
  fill(options.preset);
  const others = options.preset.others || [];
  $("#others-note").textContent = others.length
    ? `Also on Fleek today: ${others.map((s) => `${s.name} (${s.stock.length} lots, rated ${s.quality_score})`).join(", ")}. Matching chooses across every seller.`
    : "";
  $("#add-lot").addEventListener("click", () => addLot());
  $("#use-preset").addEventListener("click", () => fill(options.preset));
  $("#next").addEventListener("click", () => { if (stepValid()) showStep(step + 1); });
  $("#back").addEventListener("click", () => showStep(step - 1));
  $("#form").addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      const view = await api("/api/start", collect());
      $("#onboarding").hidden = true;
      $("#screens").hidden = false;
      $("#restart").hidden = false;
      render(view);
    } catch (error) {
      showError(error.message);
    }
  });
  $("#play").addEventListener("click", () => { setPlaying(!playing); if (playing) run(); });
  $("#step").addEventListener("click", oneTurn);
  $("#restart").addEventListener("click", () => {
    setPlaying(false);
    $("#screens").hidden = true;
    $("#onboarding").hidden = false;
    $("#restart").hidden = true;
    showStep(1);
  });
  showStep(1);
}

init();
