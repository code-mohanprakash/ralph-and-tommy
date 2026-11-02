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

const NAMES = { ralph: "Ralph", tommy: "Tommy", vault: "Vault", fleek: "Fleek",
  account_manager: "Account manager", buyer: "Buyer", seller: "Seller" };

// Every £ amount in a line, in bold: the numbers are what people watch.
function withAmounts(text) {
  const parts = text.split(/(£\d[\d,]*(?:\.\d{2})?)/);
  return parts.map((p, i) => (i % 2 ? el("strong", { class: "amount", text: p }) : document.createTextNode(p)));
}

// Who's speaking. Your own agent is "your agent"; the other side is named by its business.
function speaker(who, mine, names) {
  const agent = NAMES[who] || who;
  if (!names) return agent;
  if (who === mine) return `${agent} · your agent`;
  return names[who] ? `${agent} · for ${names[who]}` : agent;
}

function summaryCard(sum, side) {
  const row = (label, value, strong = false) =>
    el("div", { class: "sum-row" }, el("span", { text: label }), el(strong ? "strong" : "b", { text: value }));
  const rows = [
    row("Price", `${sum.price} a piece`, true),
    row("Pieces", String(sum.pieces)),
    row("Against list", sum.pct_of_list != null ? `${sum.pct_of_list}% of ${sum.list_price}` : "–"),
  ];
  if (side === "buyer") {
    rows.push(row("You pay, delivered", `${sum.you_pay} (${sum.per_piece_delivered} a piece)`));
    if (sum.under_your_top === "£0.00") rows.push(row("Against your top price", "right at it"));
    else if (sum.under_your_top) rows.push(row("Under your top price by", sum.under_your_top));
  } else if (side === "seller") {
    rows.push(row("You receive, after Fleek's 15%", sum.you_receive));
    if (sum.above_your_floor === "£0.00") rows.push(row("Against your floor", "right at it"));
    else if (sum.above_your_floor) rows.push(row("Above your floor by", sum.above_your_floor));
  }
  rows.push(row("How it went", `${sum.cards} cards, ${sum.hours}h of simulated back-and-forth`));
  const note = side === "buyer" ? "Your top price was never shown to the seller or to any AI."
    : "Your floor was never shown to the buyer or to any AI.";
  return el("li", { class: `summary${sum.closed ? " closed" : ""}` },
    el("div", { class: "sum-head" }, el("span", { class: "sum-kicker", text: "Deal summary" }),
      el("span", { class: "sum-status", text: sum.status })),
    el("div", { class: "sum-rows" }, ...rows),
    el("p", { class: "sum-note", text: note }));
}

function lineItem(line, mine, names) {
  const at = el("span", { class: "at", text: `${line.at}` });
  const cls = {
    card: `card ${line.who}${line.who === mine ? " mine" : ""}`,
    check: "check",
    stop: "stop", ask: "ask", end: "end", note: "note",
  }[line.kind] || "note";
  if (line.kind === "check") {
    return el("li", { class: cls },
      el("span", { class: "lock", text: "Private check" }),
      el("span", { class: `band ${line.band || ""}`, text: line.band || "" }),
      el("span", { class: "check-text" }, ...withAmounts(line.text)));
  }
  const head = line.kind === "card" ? el("span", { class: "speaker", text: speaker(line.who, mine, names) }) : null;
  return el("li", { class: cls }, head, at, el("span", { class: "text" }, ...withAmounts(line.text)));
}

// Re-render without replaying old entrances: only lines added since last time animate in.
function fillLines(list, items) {
  const before = Number(list.dataset.count || 0);
  items.forEach((li, i) => { if (i >= before && before > 0) li.classList.add("new"); });
  list.replaceChildren(...items);
  list.dataset.count = String(items.length);
  list.scrollTop = list.scrollHeight;
}

function renderScreen(root, data, view, side) {
  const agent = side === "buyer" ? "ralph" : "tommy";
  $('[data-field="name"]', root).textContent = data.name;
  const what = side === "buyer" ? "Your top price" : "Your floor for this lot";
  $('[data-field="secret"]', root).replaceChildren(...(data.secret ? [
    el("span", { class: "secret-label", text: what }),
    el("strong", { text: data.secret }),
    el("span", { class: "secret-note", text: "Only you and the vault see this. Never the AI." }),
  ] : []));
  $('[data-field="lot"]', root).replaceChildren(...lotBox(view, side));
  const names = { ralph: view.buyer.name, tommy: view.seller.name };
  const items = data.lines.map((l) => lineItem(l, agent, names));
  if (data.summary) items.push(summaryCard(data.summary, side));
  fillLines($('[data-field="lines"]', root), items);
  const ask = $('[data-field="ask"]', root);
  ask.hidden = !data.asked;
  if (data.asked) {
    ask.replaceChildren(
      el("p", { text: "The agents agreed. Your OK closes the deal." }),
      el("button", { class: "ok", text: "Approve", onclick: () => decide(side, "approve") }),
      el("button", { class: "bad", text: "Reject", onclick: () => decide(side, "reject") }));
  }
  // The approval box can appear below the conversation and shrink it: keep the newest line in view.
  const lines = $('[data-field="lines"]', root);
  lines.scrollTop = lines.scrollHeight;
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
  const stepTile = (n, label) => el("li", {}, el("b", { text: String(n) }), el("span", { text: label }));
  $('[data-field="funnel-steps"]', root).replaceChildren(
    stepTile(fu.lots, `lots from ${fu.sellers} sellers`),
    stepTile(fu.passed, "pass the filters"),
    stepTile(fu.possible, "the vault says a price can work"),
    stepTile(ranked, fu.rerank && fu.rerank.by === "claude" ? "ranked, then re-ranked by Ralph" : "ranked"));
  const current = view.lot ? view.lot.id : null;
  const picked = fu.rows.find((r) => r.lot === current);
  $('[data-field="picked"]', root).textContent = picked
    ? `Negotiating now: ${picked.title}, from ${picked.seller} (#${picked.ai_rank || picked.rank} of ${ranked}).`
    : "No lot can work for this buyer, so no agent is called.";
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
      const formula = `score ${r.total} = fit ${r.fit}, price ${r.price} (${r.delivered} delivered), rating ${r.quality}/5, dispatch ${r.dispatch_days} days`;
      if (r.ai_why) {
        result = r.ai_rank === r.rank ? `#${r.ai_rank}` : `#${r.ai_rank} (formula #${r.rank})`;
        why = el("div", {}, el("div", { text: `Ralph: ${r.ai_why}` }),
          el("div", { class: "muted small", text: `Formula: ${formula}` }));
      } else {
        result = `#${r.ai_rank || r.rank}`;
        why = formula;
      }
    } else if (r.step === "vault") {
      result = "no price"; why = r.why;
    } else {
      result = "filtered"; why = r.why;
    }
    const row = el("tr", { class: `${r.step}${r.lot === current ? " current" : ""}` },
      el("td", { text: r.lot === current ? `${result} ◀ now` : result }),
      el("td", { text: r.title }), el("td", { text: r.seller }),
      typeof why === "string" ? el("td", { text: why }) : el("td", {}, why));
    return row;
  }), ...(filtered ? [toggle] : []));
  const w = fu.weights;
  $('[data-field="weights"]', root).textContent =
    `Ranking uses public facts only, weighted fit ${w.fit}, price ${w.price}, seller rating ${w.quality}, dispatch ${w.speed} (market.toml). ` +
    (fu.rerank && fu.rerank.by === "claude"
      ? `Then Claude re-orders the top ${fu.rerank.shortlist} on the buyer's own words, from the same public facts (no seller description), and gives a reason for each; code checks every lot appears once. `
      : "With scripted agents the formula's order stands. ") +
    `The vault's yes or no is the only part that touches a secret, and it never gives a number.`;
}

function renderMetrics(root, m) {
  const t = m.totals;
  const pairs = [
    ["Agent turns", t.agent_turns], ["Model calls", t.model_calls],
    ["Tokens", `${t.tokens_in.toLocaleString("en-GB")} in · ${t.tokens_out.toLocaleString("en-GB")} out`], ["AI cost", `${t.cost_cents}¢`],
    ["Agent time", `${t.wall_seconds}s`], ["Lots tried", t.lots_tried], ["Cards", t.cards],
    ["Simulated time", `${t.simulated_hours}h`], ["Deal price", t.price_vs_list || "–"],
    ["Vault stops", t.vault_stops],
  ];
  $('[data-field="metrics"]', root).replaceChildren(...pairs.map(([k, v]) =>
    el("div", { class: String(v).length > 12 ? "tile wide" : "tile" }, el("b", { text: String(v) }), el("span", { text: k }))));
}

function render(view) {
  last = view;
  $("#agents-label").textContent = view.agents;
  $("#clock").hidden = false;
  $("#clock").textContent = view.time;
  renderScreen($("#buyer-screen"), view.buyer, view, "buyer");
  renderScreen($("#seller-screen"), view.seller, view, "seller");
  const f = $("#fleek-screen");
  renderFunnel($("#match-screen"), view);
  renderMetrics(f, view.fleek.metrics);
  fillLines($('[data-field="lines"]', f), view.fleek.lines.map((l) =>
    lineItem(l, "", { ralph: view.buyer.name, tommy: view.seller.name })));
  const deal = $('[data-field="deal"]', f);
  const fs = view.fleek.summary;
  deal.hidden = !fs;
  if (fs) {
    const tile = (v, k) => el("div", { class: "tile" }, el("b", { text: String(v) }), el("span", { text: k }));
    deal.replaceChildren(
      el("div", { class: "deal-head" }, el("h3", { text: "The deal" }), el("span", { class: "sum-status", text: fs.status })),
      el("div", { class: "deal-tiles" },
        tile(`${fs.price}`, `a piece, ${fs.pct_of_list}% of list`),
        tile(fs.pieces, "pieces"),
        tile(fs.order_value, "order value"),
        tile(fs.commission, "Fleek's 15% commission"),
        tile(fs.protection_fee, "buyer protection fee"),
        tile(`${fs.cards} cards`, `${fs.hours}h simulated`),
        tile(`${fs.ai_cost_cents}¢`, `AI cost, ${fs.model_calls} calls`),
        tile(fs.vault_stops, "moves the vault stopped")));
  }
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
  box.dataset.tone = view.over ? "over" : view.waiting ? "waiting" : view.paused ? "paused" : thinking ? "thinking" : "live";
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
  $("#toggle-match").addEventListener("click", () => {
    const body = $('[data-field="match-body"]');
    const open = body.hidden;
    body.hidden = !open;
    $("#toggle-match").textContent = open ? "Hide matching" : "Show how it was matched";
    $("#toggle-match").setAttribute("aria-expanded", String(open));
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
