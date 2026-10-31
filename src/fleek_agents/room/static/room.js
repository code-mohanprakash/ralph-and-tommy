// The Deal Room page. It asks the server to run a negotiation, then acts out the steps it gets
// back. It decides nothing itself: every price, answer and outcome comes from the Python code.
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const money = (p) => "£" + (p / 100).toLocaleString("en-GB", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const calm = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // ---------- the 3D scene (shapes from the case-study mockup) ----------
  const box = $("scene");
  let W = box.clientWidth || 900, H = box.clientHeight || 440;
  const HW = 13.3;
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1));
  renderer.setSize(W, H);
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  box.appendChild(renderer.domElement);
  const scene = new THREE.Scene();
  const cam = new THREE.OrthographicCamera(-HW, HW, HW, -HW, 0.1, 200);
  function frameCamera() {
    // Show the whole board at any width: at least HW across and 7.9 up and down, nudged up a
    // little so the warehouse labels at the back stay in view.
    const aspect = W / H, halfH = Math.max(HW / aspect, 7.9), halfW = halfH * aspect, up = 0.7;
    Object.assign(cam, { left: -halfW, right: halfW, top: halfH + up, bottom: -halfH + up });
    cam.updateProjectionMatrix();
  }
  frameCamera();
  cam.position.set(0, 20, 22);
  cam.lookAt(0, 0.4, 0);
  scene.add(new THREE.HemisphereLight(0xffffff, 0xb9b2a0, 0.8));
  const sun = new THREE.DirectionalLight(0xffffff, 0.7);
  sun.position.set(-6, 18, 10);
  sun.castShadow = true;
  sun.shadow.mapSize.set(2048, 2048);
  Object.assign(sun.shadow.camera, { left: -16, right: 16, top: 14, bottom: -14, near: 1, far: 60 });
  sun.shadow.camera.updateProjectionMatrix();
  sun.shadow.bias = -0.0005;
  scene.add(sun);

  const mat = (c, e) => new THREE.MeshLambertMaterial({ color: c, emissive: e || 0 });
  const V = (x, y, z) => new THREE.Vector3(x, y, z);
  const BX = (w, h, d) => new THREE.BoxGeometry(w, h, d);
  function mk(geo, m, x, y, z, parent) {
    const o = new THREE.Mesh(geo, typeof m === "number" ? mat(m) : m);
    o.position.set(x, y, z);
    o.castShadow = true;
    o.receiveShadow = true;
    (parent || scene).add(o);
    return o;
  }

  // Ground, road, trees.
  mk(BX(25, 0.8, 17), 0xEDE8DC, 0, -0.4, 0.3);
  mk(BX(25.3, 0.4, 17.3), 0xD3CCBA, 0, -1.0, 0.3);
  mk(BX(22, 0.04, 1.3), 0xA8A69E, 0, 0.02, 7.2);
  for (let x = -10; x <= 10; x += 1.6) mk(BX(0.7, 0.05, 0.1), 0xF1EFE8, x, 0.05, 7.2);
  [[-11.3, -6.8], [-4, -7], [3.5, -7.2], [-11.5, 4.8], [2.6, 4.6], [-2.8, 4.4]].forEach(([x, z]) => {
    mk(new THREE.CylinderGeometry(0.15, 0.18, 0.6, 8), 0x854F0B, x, 0.3, z);
    mk(new THREE.ConeGeometry(0.75, 1.7, 10), 0x97C459, x, 1.4, z);
  });

  // The shop on Brick Lane.
  const SHOP = V(-9, 0, -1);
  mk(BX(3.4, 2.4, 3), 0xFAF6EC, SHOP.x, 1.2, SHOP.z);
  const roof = mk(new THREE.ConeGeometry(2.6, 1.5, 4), 0x7F77DD, SHOP.x, 3.15, SHOP.z);
  roof.rotation.y = Math.PI / 4;
  mk(BX(0.9, 1.3, 0.06), 0x534AB7, SHOP.x + 0.7, 0.65, SHOP.z + 1.53);
  mk(BX(1.0, 0.7, 0.06), 0xB5D4F4, SHOP.x - 0.8, 1.3, SHOP.z + 1.53);
  const awning = mk(BX(3.6, 0.12, 0.9), 0xAFA9EC, SHOP.x, 2.0, SHOP.z + 1.9);
  awning.rotation.x = 0.3;

  // The vault: a safe with a dial and a lamp on top.
  mk(BX(2.9, 0.3, 2.9), 0xB4B2A9, 0, 0.15, -0.6);
  mk(BX(2.1, 2.1, 2.1), 0x5F5E5A, 0, 1.35, -0.6);
  const dial = new THREE.Group();
  dial.position.set(0, 1.35, 0.5);
  scene.add(dial);
  mk(new THREE.CylinderGeometry(0.55, 0.55, 0.12, 28), 0xD3D1C7, 0, 0, 0, dial).rotation.x = Math.PI / 2;
  for (let k = 0; k < 3; k++) mk(BX(1.4, 0.1, 0.08), 0x888780, 0, 0, 0.08, dial).rotation.z = (k * Math.PI) / 3;
  const lampMat = mat(0x888780);
  mk(new THREE.SphereGeometry(0.28, 16, 12), lampMat, 0, 2.72, -0.6);

  // Three warehouses, keyed by seller id.
  const WH = {
    "seller-9001": { z: -5.6 }, "seller-9002": { z: -0.6 }, "seller-9003": { z: 4.4 },
  };
  for (const id in WH) {
    const z = WH[id].z;
    mk(BX(3.6, 2.4, 3.2), 0xF1EFE8, 9, 1.2, z);
    WH[id].roof = mk(BX(3.9, 0.35, 3.5), 0x1D9E75, 9, 2.57, z);
    mk(BX(1.6, 1.6, 0.06), 0x444441, 9, 0.8, z + 1.62);
    mk(BX(0.55, 0.55, 0.55), 0x378ADD, 11.3, 0.28, z + 0.3);
    mk(BX(0.55, 0.55, 0.55), 0x185FA5, 11.3, 0.28, z + 0.9);
    mk(BX(0.55, 0.55, 0.55), 0x378ADD, 11.3, 0.83, z + 0.6);
  }

  // The agents: Ralph by the shop, a Tommy by each warehouse.
  function bot(colour, x, z, turn) {
    const g = new THREE.Group();
    g.position.set(x, 0, z);
    g.rotation.y = turn;
    scene.add(g);
    mk(new THREE.CylinderGeometry(0.42, 0.52, 1.0, 18), colour, 0, 0.5, 0, g);
    mk(new THREE.SphereGeometry(0.46, 20, 16), 0xFAF8F2, 0, 1.45, 0, g);
    mk(BX(0.62, 0.2, 0.12), 0x2C2C2A, 0, 1.5, 0.4, g);
    mk(new THREE.CylinderGeometry(0.035, 0.035, 0.38, 8), 0x5F5E5A, 0, 2.06, 0, g);
    const bulb = mat(0xEF9F27);
    mk(new THREE.SphereGeometry(0.12, 12, 10), bulb, 0, 2.28, 0, g);
    const ring = new THREE.Mesh(new THREE.RingGeometry(0.75, 0.95, 32), new THREE.MeshBasicMaterial({ color: 0xEF9F27, side: THREE.DoubleSide }));
    ring.rotation.x = -Math.PI / 2;
    ring.position.set(x, 0.03, z);
    ring.visible = false;
    scene.add(ring);
    return { g, bulb, ring, hop: 0, turn, home: V(x, 0, z) };
  }
  const BOTS = { ralph: bot(0x7F77DD, -6.2, 0.8, 0.7) };
  for (const id in WH) BOTS[id] = bot(0x1D9E75, 6.3, WH[id].z + 1.1, -0.7);

  // Things that move: an offer card, a gold coin (a secret), the delivery truck.
  const cardMat = mat(0xFFFFFF);
  const card = mk(BX(1.1, 0.08, 0.75), cardMat, 0, -5, 0);
  card.visible = false;
  const stripe = mk(BX(1.1, 0.1, 0.18), 0x7F77DD, 0, 0.01, -0.26, card);
  const coins = [0, 1, 2].map(() => {
    const c = mk(new THREE.CylinderGeometry(0.38, 0.38, 0.12, 24), mat(0xEF9F27, 0x633806), 0, -5, 0);
    c.rotation.x = Math.PI / 2;
    c.visible = false;
    return c;
  });
  const truck = new THREE.Group();
  truck.visible = false;
  scene.add(truck);
  mk(BX(2.2, 1.0, 1.2), 0xF6F4EE, 0.45, 0.85, 0, truck);
  mk(BX(1.0, 1.0, 1.15), 0xD85A30, -0.95, 0.85, 0, truck);
  mk(BX(0.06, 0.45, 0.95), 0x2C2C2A, -1.47, 1.05, 0, truck);
  const wheels = [];
  for (const wx of [-0.9, 0.9]) for (const wz of [-0.6, 0.6]) {
    const w = mk(new THREE.CylinderGeometry(0.3, 0.3, 0.22, 14), 0x2C2C2A, wx, 0.3, wz, truck);
    w.rotation.x = Math.PI / 2;
    wheels.push(w);
  }
  [[0, 1.6, -0.28], [0, 1.6, 0.3], [0.9, 1.6, 0]].forEach(([x, y, z]) => mk(BX(0.5, 0.5, 0.5), 0x378ADD, x, y, z, truck));

  // HTML labels that follow points in the scene.
  const labels = [];
  function label(cls, text, at) {
    const e = document.createElement("div");
    e.className = cls;
    e.textContent = text;
    box.appendChild(e);
    const o = { e, at };
    labels.push(o);
    return o;
  }
  label("lb", "Vintage shop · Brick Lane", () => V(-9, 4.1, -1));
  const vaultLabel = label("lb dn", "Fleek vault", () => V(0, 0.3, 0.9));
  label("lb dn", "Ralph · the shop's AI", () => BOTS.ralph.g.position.clone().add(V(0, 0, 0.9)));
  const PLACE = { "seller-9001": "Lahore · Pakistan", "seller-9002": "Karachi · Pakistan", "seller-9003": "Delhi · India" };
  // On the open ground to the left of each Tommy: above a roof or at a door, a label lines up with
  // the next warehouse along in this camera angle.
  for (const id in WH) WH[id].label = label("lb dn", PLACE[id], () => V(3.9, 0.05, WH[id].z + 1.0));
  const bubbles = {};
  for (const k in BOTS) bubbles[k] = label("bb", "", () => BOTS[k].g.position.clone().add(V(0, 2.75, 0)));
  bubbles.shop = label("bb", "", () => V(-9, 4.6, -1));
  bubbles.vault = label("bb", "", () => V(0, 3.4, -0.6));
  const cardLabel = label("cl", "", () => card.position.clone().add(V(0, 0.45, 0)));
  function placeLabels() {
    for (const o of labels) {
      const p = o.at().project(cam);
      o.e.style.left = ((p.x + 1) / 2) * W + "px";
      o.e.style.top = ((1 - p.y) / 2) * H + "px";
    }
  }

  // ---------- tweens: small animations, all finished at once when the person skips ahead ----------
  let tweens = [], speed = 1, paused = false;
  const ease = (p) => (p < 0.5 ? 2 * p * p : 1 - Math.pow(-2 * p + 2, 2) / 2);
  function tween(ms, fn) {
    return new Promise((resolve) => {
      if (calm) { fn(1); resolve(); return; }
      tweens.push({ t: 0, d: ms, fn, resolve });
    });
  }
  const wait = (ms) => tween(ms, () => {});
  function finishAll() {
    const all = tweens;
    tweens = [];
    for (const t of all) { t.fn(1); t.resolve(); }
  }

  let last = performance.now(), clock = 0;
  const botKeys = Object.keys(BOTS);
  function frame(now) {
    const dt = Math.min(0.05, (now - last) / 1000);
    last = now;
    clock += dt;
    const step = paused ? 0 : dt * 1000 * speed;
    for (let i = tweens.length - 1; i >= 0; i--) {
      const t = tweens[i];
      t.t += step;
      const p = Math.min(1, t.t / t.d);
      t.fn(p);
      if (p >= 1) { tweens.splice(i, 1); t.resolve(); }
    }
    botKeys.forEach((k, i) => {
      const b = BOTS[k];
      b.g.position.y = b.hop + (calm ? 0 : Math.abs(Math.sin(clock * 2 + i * 1.3)) * 0.05);
    });
    placeLabels();
    renderer.render(scene, cam);
    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
  window.addEventListener("resize", () => {
    W = box.clientWidth || W;
    H = box.clientHeight || H;
    frameCamera();
    renderer.setSize(W, H);
  });

  // ---------- moves the steps animate ----------
  const hand = (who) => BOTS[who].g.position.clone().add(V(0, 1.9, 0));
  const VAULT_TOP = V(0, 3.15, -0.6);
  function fly(obj, from, to, ms, height) {
    return tween(ms, (p) => {
      const e = ease(p);
      obj.position.lerpVectors(from, to, e);
      obj.position.y += Math.sin(Math.PI * e) * height;
      obj.rotation.y = e * Math.PI * 2;
    });
  }
  function lamp(state) {
    const c = { ok: [0x639922, 0x27500A], bad: [0xE24B4A, 0x791F1F], gold: [0xEF9F27, 0x854F0B], idle: [0x888780, 0] }[state];
    lampMat.color.setHex(c[0]);
    lampMat.emissive.setHex(c[1]);
  }
  function setVaultLabel(text, cls) {
    vaultLabel.e.textContent = text;
    vaultLabel.e.className = "lb dn" + (cls ? " " + cls : "");
  }
  function say(who, text) {
    const b = bubbles[who];
    b.e.textContent = text;
    b.e.style.opacity = text ? 1 : 0;
  }
  async function think(who, text, ms) {
    say(who, text);
    BOTS[who] && BOTS[who].bulb.emissive.setHex(0xBA7517);
    await tween(ms, (p) => { if (BOTS[who]) BOTS[who].hop = Math.abs(Math.sin(p * Math.PI * 2)) * 0.3; });
    if (BOTS[who]) { BOTS[who].hop = 0; BOTS[who].bulb.emissive.setHex(0); }
  }
  async function stamp(ok) {
    lamp(ok ? "ok" : "bad");
    setVaultLabel(ok ? "✓ Allowed" : "✗ Not allowed", ok ? "good" : "bad");
    const r0 = dial.rotation.z;
    await tween(700, (p) => {
      dial.rotation.z = r0 + ease(p) * Math.PI * (ok ? 2 : -1);
      card.position.y = VAULT_TOP.y + Math.sin(p * Math.PI) * 0.15;
    });
  }
  async function sendCard(from, to, text, ok, gold) {
    card.visible = true;
    cardMat.color.setHex(gold ? 0xFAC775 : 0xFFFFFF);
    stripe.material.color.setHex(ok === false ? 0xE24B4A : from === "ralph" ? 0x7F77DD : 0x1D9E75);
    card.position.copy(hand(from));
    cardLabel.e.textContent = text;
    cardLabel.e.style.opacity = 1;
    await fly(card, hand(from), VAULT_TOP, 900, 1.6);
    await stamp(ok);
    if (to) {
      await fly(card, VAULT_TOP, ok ? hand(to) : hand(from), ok ? 900 : 750, ok ? 1.6 : 1.0);
      if (!ok) {
        const b = BOTS[from];
        await tween(600, (p) => { b.g.rotation.y = b.turn + Math.sin(p * Math.PI * 4) * 0.35; });
        b.g.rotation.y = b.turn;
      }
    }
    card.visible = false;
    cardLabel.e.style.opacity = 0;
  }
  async function coinsToVault(froms) {
    froms.forEach((from, i) => { coins[i].visible = true; coins[i].scale.setScalar(1); coins[i].position.copy(from); });
    lamp("gold");
    await tween(1100, (p) => {
      const e = ease(p);
      froms.forEach((from, i) => {
        coins[i].position.lerpVectors(from, VAULT_TOP, e);
        coins[i].position.y += Math.sin(Math.PI * e) * 2.2;
        coins[i].rotation.y = e * Math.PI * 4;
      });
    });
    await tween(300, (p) => froms.forEach((_, i) => coins[i].scale.setScalar(1 - p * 0.9)));
    coins.forEach((c) => (c.visible = false));
    setVaultLabel("Locked away", "gold");
  }
  async function driveTruck(fromSeller) {
    const z = WH[fromSeller].z;
    truck.position.set(8.2, 0, 7.2);
    truck.scale.setScalar(0.01);
    truck.visible = true;
    await tween(400, (p) => truck.scale.setScalar(0.01 + 0.99 * ease(p)));
    const x0 = truck.position.x;
    await tween(3000, (p) => {
      truck.position.x = x0 + (-6.6 - x0) * ease(p);
      for (const w of wheels) w.rotation.y = -p * 30;
    });
    say("ralph", "Delivered to Brick Lane");
    void z;
  }

  // ---------- the story: state worked out from steps 0..i, then the step itself acted out ----------
  let story = null, at = -1, playing = false, run = 0;
  const CITY = { "seller-9001": "Lahore", "seller-9002": "Karachi", "seller-9003": "Delhi" };
  const MEANS = { strong: "very good for you", acceptable: "fine for you", stretch: "allowed, but close to your limit", outside: "past your limit" };

  function stateUpTo(i) {
    const s = {
      roof: {}, ring: {}, place: {}, vault: ["Fleek vault", ""], lamp: "idle", secrets: [],
      ralph: [], tommy: [], ralphHint: null, tommyHint: null, check: null, cards: [],
      matched: null, money: false, waiting: false, decided: null,
    };
    for (const id in WH) { s.roof[id] = 0x1D9E75; s.ring[id] = false; s.place[id] = [PLACE[id], ""]; }
    for (let j = 0; j <= i; j++) {
      const st = story.steps[j];
      const id = st.seller_id;
      switch (st.kind) {
        case "tell": s.ralph.push("The shop wants: " + story.buyer.wants); break;
        case "secret":
          if (st.actor === "buyer") s.secrets.push("buyer");
          else s.secrets.push("sellers");
          s.vault = ["Locked away", "gold"];
          break;
        case "filter": s.roof[id] = 0xB4B2A9; s.place[id] = [CITY[id] + " · filtered out", "bad"]; s.check = st; break;
        case "check":
          s.check = st;
          if (st.ok) { s.ring[id] = true; s.place[id] = [CITY[id] + " · vault: yes", "good"]; }
          else { s.roof[id] = 0xB4B2A9; s.place[id] = [CITY[id] + " · vault: no", "bad"]; }
          break;
        case "matched": {
          s.matched = id;
          for (const k in WH) if (k !== id && s.place[k][1] !== "bad") s.place[k] = [CITY[k] + " · not chosen", ""];
          for (const k in WH) s.ring[k] = k === id;
          s.place[id] = [CITY[id] + " · matched", "good"];
          const x = story.sellers.find((y) => y.id === id);
          s.tommy.push(x.lot + ", list " + money(x.list_price) + " a pair");
          s.tommy.push(story.buyer.pairs + " pairs wanted");
          s.ralph.push("Matched: " + CITY[id] + ", list " + money(x.list_price) + " a pair");
          s.check = st;
          break;
        }
        case "card": case "blocked": case "accept": case "walk":
          if (st.band) {
            const hint = { price: st.asked, band: st.band };
            if (st.actor === "ralph") s.ralphHint = hint; else s.tommyHint = hint;
          }
          if (st.kind === "card") s.cards.push(st);
          if (st.kind !== "walk") s.check = st;
          if (st.kind === "accept") { s.roof[s.matched] = 0xEF9F27; s.place[s.matched] = [CITY[s.matched] + " · deal", "gold"]; }
          if (st.kind === "blocked") s.place[s.matched] = [CITY[s.matched] + " · stopped", "bad"];
          if (st.kind === "walk") { s.ring[s.matched] = false; s.place[s.matched] = [CITY[s.matched] + " · no deal", "bad"]; }
          break;
        case "money": s.money = true; break;
        case "waiting": s.waiting = true; break;
        case "approved": s.decided = "approved"; break;
        case "decided": s.decided = st.ok ? "approved" : "rejected"; s.waiting = false; break;
      }
    }
    if (s.decided === "rejected") { s.roof[s.matched] = 0x1D9E75; s.place[s.matched] = [CITY[s.matched] + " · back on sale", ""]; }
    return s;
  }

  function li(list, items) {
    list.innerHTML = "";
    for (const text of items) {
      const e = document.createElement("li");
      e.textContent = text;
      list.appendChild(e);
    }
  }
  function hintText(el, h) {
    if (!h) { el.textContent = "none yet"; el.className = "hint muted"; return; }
    el.className = "hint";
    el.innerHTML = "";
    el.append(money(h.price) + "? ");
    const b = document.createElement("b");
    b.textContent = "“" + h.band + "”";
    b.className = h.band === "outside" ? "bad" : h.band === "stretch" ? "secret" : "good";
    el.append(b, " (" + MEANS[h.band] + ")");
  }
  function cardsLine(cards) {
    return cards.length ? "Cards so far: " + cards.map((c) => (c.actor === "ralph" ? "R " : "T ") + money(c.price)).join(" → ") : null;
  }

  function render(i) {
    const s = stateUpTo(i), st = story.steps[i], peek = $("peek").checked;
    for (const id in WH) {
      WH[id].roof.material.color.setHex(s.roof[id]);
      BOTS[id].ring.visible = s.ring[id];
      WH[id].label.e.textContent = s.place[id][0];
      WH[id].label.e.className = "lb dn" + (s.place[id][1] ? " " + s.place[id][1] : "");
    }
    lamp(s.lamp);
    setVaultLabel(s.vault[0], s.vault[1]);
    for (const k in bubbles) say(k, "");
    card.visible = false;
    cardLabel.e.style.opacity = 0;
    coins.forEach((c) => (c.visible = false));
    truck.visible = s.decided === "approved" && st.kind !== "decided" && st.kind !== "approved";
    if (truck.visible) { truck.position.set(-6.6, 0, 7.2); truck.scale.setScalar(1); }

    $("stepNo").textContent = (i + 1) + " of " + story.steps.length;
    $("say").textContent = st.say;
    $("detail").textContent = st.detail;
    $("detail").hidden = !$("eng").checked;
    $("decide").hidden = !(s.waiting && i === story.steps.length - 1);

    const cl = cardsLine(s.cards);
    li($("ralphKnows"), s.ralph.concat(cl ? [cl] : []).concat(s.ralph.length ? [] : ["nothing yet"]));
    li($("tommyKnows"), s.tommy.concat(cl ? [cl] : []).concat(s.tommy.length ? [] : ["nothing yet"]));
    hintText($("ralphHint"), s.ralphHint);
    hintText($("tommyHint"), s.tommyHint);

    const holds = [];
    const a = story.audience;
    if (s.secrets.includes("buyer")) holds.push(["The shop's max, a pair delivered", peek ? money(a.buyer_max) : "£••.••"]);
    if (s.secrets.includes("sellers")) holds.push(["Karachi's floor, a pair after the fee", peek ? money(a.seller_floor) : "£••.••"]);
    const ul = $("vaultHolds");
    ul.innerHTML = "";
    if (!holds.length) ul.innerHTML = "<li class='muted'>nothing yet</li>";
    for (const [k, v] of holds) {
      const e = document.createElement("li");
      e.textContent = k + ": ";
      const b = document.createElement("span");
      b.className = peek ? "secret" : "masked";
      b.textContent = v;
      e.appendChild(b);
      ul.appendChild(e);
    }
    if (peek && s.secrets.length === 2 && a.buyer_highest_card != null && a.seller_lowest_card != null) {
      const e = document.createElement("li");
      e.className = "muted";
      e.textContent = "As card prices: from " + money(a.seller_lowest_card) + " to " + money(a.buyer_highest_card) + " can work";
      ul.appendChild(e);
    }
    const c = s.check, vc = $("vaultCheck");
    if (!c) { vc.textContent = "none yet"; vc.className = "muted"; }
    else {
      vc.className = c.ok === false ? "bad" : "good";
      vc.textContent = (c.ok === false ? "✗ " : "✓ ") + checkText(c);
    }
    $("money").hidden = !s.money;
    if (s.money) {
      $("mBuy").textContent = money(story.outcome.buyer_pays);
      $("mSell").textContent = money(story.outcome.seller_gets);
      $("mFleek").textContent = money(story.outcome.fleek_earns);
    }
    document.querySelectorAll(".panel").forEach((p) => p.classList.remove("active"));
    $("back").disabled = i <= 0;
    $("next").disabled = i >= story.steps.length - 1;
    return s;
  }
  function checkText(c) {
    const city = CITY[c.seller_id] || "";
    switch (c.kind) {
      case "filter": return city + " dropped by the filters (no secret used)";
      case "check": return "Could any price work with " + city + "? " + (c.ok ? "Yes" : "No");
      case "matched": return city + " matched";
      case "card": return money(c.price) + " is inside " + (c.actor === "ralph" ? "the shop's" : "the warehouse's") + " own limit";
      case "blocked": return money(c.price || 0) + " is past " + (c.actor === "ralph" ? "the shop's" : "the warehouse's") + " limit. Not sent";
      case "accept": return money(c.price) + " is inside both limits";
      default: return "";
    }
  }

  async function act(i) {
    const mine = ++run;
    finishAll();
    const s = render(i), st = story.steps[i];
    const gone = () => mine !== run;
    const shopper = (who) => (who === "ralph" ? "ralph" : s.matched);
    switch (st.kind) {
      case "tell": await think("ralph", "200 pairs of Levi's 501, grade A. Got it.".replace("200", story.buyer.pairs), 1600); break;
      case "secret":
        setVaultLabel("Fleek vault", "");
        lamp("idle");
        if (st.actor === "buyer") await coinsToVault([V(-9, 3.6, -1)]);
        else await coinsToVault(Object.keys(WH).map((id) => V(9, 3, WH[id].z)));
        break;
      case "list":
        for (const x of story.sellers) say(x.id, x.city + ": list " + money(x.list_price));
        await wait(2200);
        break;
      case "check": case "filter":
        lamp(st.ok ? "ok" : "bad");
        say("vault", st.kind === "filter" ? "Filtered out" : st.ok ? "Yes" : "No");
        await wait(1400);
        break;
      case "matched": lamp("ok"); await think(st.seller_id, "I'll sell to the shop", 1200); break;
      case "card": case "blocked": {
        const who = shopper(st.actor);
        if (st.asked != null) await think(who, money(st.asked) + "? The vault says “" + st.band + "”", 1300);
        if (gone()) return;
        say(who, "");
        const to = st.kind === "card" ? shopper(st.target) : st.actor === "ralph" ? s.matched : "ralph";
        await sendCard(who, to, money(st.price || 0) + " a pair", st.kind === "card");
        if (gone()) return;
        if (st.kind === "blocked") say("vault", "Stopped. A person takes over.");
        break;
      }
      case "accept": {
        const who = shopper(st.actor);
        if (st.asked != null) await think(who, money(st.asked) + "? The vault says “" + st.band + "”", 1300);
        if (gone()) return;
        say(who, "");
        await sendCard(who, null, "Deal: " + money(st.price) + " a pair", true, true);
        lamp("gold");
        break;
      }
      case "walk": await think(shopper(st.actor), "I'm walking away", 1400); break;
      case "waiting": lamp("gold"); say("vault", "Waiting for a person at Fleek"); break;
      case "approved": case "decided":
        if (st.ok !== false && s.matched) await driveTruck(s.matched);
        break;
      case "no_match": lamp("bad"); say("vault", "No warehouse can work"); break;
    }
  }

  function go(i) {
    if (!story) return;
    at = Math.max(0, Math.min(story.steps.length - 1, i));
    return act(at);
  }
  async function playAll() {
    playing = true;
    $("play").textContent = "Pause";
    while (playing && story && at < story.steps.length - 1) {
      await go(at + 1);
      if (!playing) break;
      await wait(story.steps[at].kind === "secret" ? 600 : 1400);
    }
    stop();
  }
  function stop() {
    playing = false;
    $("play").textContent = story && at >= story.steps.length - 1 ? "Play again" : "Play";
  }

  $("play").onclick = () => {
    if (playing) { stop(); return; }
    if (story && at >= story.steps.length - 1) at = -1;
    playAll();
  };
  $("next").onclick = () => { stop(); go(at + 1); };
  $("back").onclick = () => { stop(); go(at - 1); };
  $("restart").onclick = () => { stop(); go(0); };
  $("speed").onclick = () => { speed = speed === 1 ? 2 : 1; $("speed").textContent = "Speed " + speed + "x"; };
  $("peek").onchange = () => story && render(at);
  $("eng").onchange = () => story && render(at);
  document.addEventListener("keydown", (e) => {
    if (e.target.closest("input, select, textarea")) return;
    if (e.key === "ArrowRight") $("next").click();
    if (e.key === "ArrowLeft") $("back").click();
    if (e.key === " ") { e.preventDefault(); $("play").click(); }
  });

  async function post(path, body) {
    const r = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const data = await r.json();
    if (!r.ok) throw new Error(data.error || "Something went wrong.");
    return data;
  }
  function readSetup() {
    const pence = (v) => Math.round(parseFloat(v) * 100);
    const body = {
      buyer_max: pence($("max").value), seller_floor: pence($("floor").value),
      pairs: parseInt($("pairs").value, 10), regular_buyer: $("regular").checked,
    };
    if (!(body.buyer_max > 0) || !(body.seller_floor > 0)) throw new Error("Enter both secret limits in pounds, for example 15.50 and 9.35.");
    return body;
  }
  async function start(body) {
    $("err").textContent = "";
    stop();
    try {
      story = await post("/api/run", body);
      for (const id in WH) BOTS[id].ring.visible = false;
      go(0);
    } catch (e) {
      $("err").textContent = e.message;
    }
  }
  $("run").onclick = () => {
    try { start(readSetup()); } catch (e) { $("err").textContent = e.message; }
  };
  ["max", "floor"].forEach((id) => $(id).addEventListener("input", () => ($("err").textContent = "")));

  async function decide(decision) {
    try {
      const r = await post("/api/decide", { decision });
      story.steps.push({ actor: "person", kind: "decided", say: r.say, detail: "approve()/reject() → " + r.state, ok: decision === "approve" });
      stop();
      go(story.steps.length - 1);
    } catch (e) {
      $("err").textContent = e.message;
    }
  }
  $("approve").onclick = () => decide("approve");
  $("reject").onclick = () => decide("reject");

  start(readSetup());
})();
