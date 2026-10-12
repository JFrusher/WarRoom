"use strict";

const socket = io();
const el = (id) => document.getElementById(id);

// Attack surface tally — the vectors the range exposes.
const vectorCounts = { sqli: 0, cmdi: 0, xss: 0, idor: 0, ssrf: 0 };
const techniques = new Set();

function setConnected(ok) {
  el("conn-dot").className = "dot" + (ok ? "" : " off");
  el("conn-text").textContent = ok ? "live" : "disconnected";
}

function renderScores(scores) {
  el("score-red").textContent = scores.red;
  el("score-blue").textContent = scores.blue;
  const total = scores.red + scores.blue;
  const red = total ? (100 * scores.red) / total : 50;
  el("bar-red").style.width = red + "%";
  el("bar-blue").style.width = (100 - red) + "%";
}

// Small helper: an element with a class and plain text (text is never HTML).
function span(cls, text) {
  const s = document.createElement("span");
  if (cls) s.className = cls;
  if (text != null) s.textContent = text;
  return s;
}
function row(className, ...kids) {
  const r = document.createElement("div");
  r.className = className;
  kids.forEach((k) => r.appendChild(k));
  return r;
}

function renderMitigations(mitigations) {
  const wrap = el("mitigations");
  wrap.replaceChildren();
  for (const [vector, patched] of Object.entries(mitigations)) {
    const state = span("state");
    state.appendChild(span("mark " + (patched ? "patched" : "exposed")));
    state.append(vector);
    wrap.appendChild(row("rowline", state,
      span("tag " + (patched ? "patched" : "exposed"), patched ? "patched" : "exposed")));
  }
}

function renderVectorTally() {
  const wrap = el("vector-tally");
  wrap.replaceChildren();
  for (const [v, n] of Object.entries(vectorCounts)) {
    wrap.appendChild(row("rowline",
      span("name" + (n ? "" : " idle"), v),
      span("val tnum" + (n ? " hot" : ""), n)));
  }
}

function renderTechniques() {
  const wrap = el("attack");
  wrap.replaceChildren();
  for (const t of [...techniques].sort()) wrap.appendChild(span("", t));
}

function describe(e) {
  const v = e.vector || (e.vectors || []).join(" ");
  switch (e.kind) {
    case "thought":         return { text: e.rationale || "", cls: "think" };
    case "exploit_attempt": return { text: `${v} attempt` };
    case "exploit_success": return { text: `${v} payload landed` };
    case "flag_captured":   return { text: `${v} flag captured`, pts: e.points, cls: "cap" };
    case "exploit_failed":  return { text: `${v} blocked`, cls: "miss" };
    case "detection":       return { text: `detect ${v} src=${e.ip || "?"} score=${e.score ?? ""}` };
    case "mitigation":      return { text: `patch ${v}` };
    case "block":           return { text: `block ${e.ip || ""} rate-limited` };
    case "throttle":        return { text: `throttle ${e.ip || ""}` };
    case "campaign_stage":  return { text: `stage ${v}` };
    default:                return { text: `${e.kind} ${v}`.trim() };
  }
}

function pushEvent(event) {
  const d = describe(event);
  const side = event.team === "red" ? "red" : event.team === "blue" ? "blue" : "sys";
  const t = new Date(event.ts).toLocaleTimeString("en-GB");
  const li = document.createElement("li");
  if (d.cls) li.className = d.cls;
  li.append(span("t", t), span("side " + side, side), span("msg", d.text));
  if (typeof d.pts === "number" && d.pts) li.append(" ", span("pts", "+" + d.pts));
  const feed = el("feed");
  feed.prepend(li);
  while (feed.childElementCount > 40) feed.lastChild.remove();

  for (const v of event.vectors || (event.vector ? [event.vector] : [])) {
    if (v in vectorCounts) vectorCounts[v] += 1;
  }
  for (const tq of event.techniques || []) techniques.add(tq);
  renderVectorTally();
  renderTechniques();
}

socket.on("connect", () => setConnected(true));
socket.on("disconnect", () => setConnected(false));

socket.on("snapshot", (snap) => {
  renderScores(snap.scores);
  renderMitigations(snap.mitigations);
  el("uptime").textContent = `${snap.uptime}%`;
  el("feed").innerHTML = "";
  for (const v of Object.keys(vectorCounts)) vectorCounts[v] = 0;
  techniques.clear();
  // Oldest first so prepend leaves newest on top.
  [...snap.events].forEach(pushEvent);
});

socket.on("scores", renderScores);
socket.on("mitigations", renderMitigations);
socket.on("sla", (data) => (el("uptime").textContent = `${data.uptime}%`));
socket.on("event", pushEvent);

renderVectorTally();
renderTechniques();
