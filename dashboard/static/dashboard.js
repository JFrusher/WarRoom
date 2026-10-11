"use strict";

const socket = io();

const el = (id) => document.getElementById(id);
const vectorCounts = { sqli: 0, xss: 0, cmdi: 0 };

const chart = new Chart(el("score-chart"), {
  type: "bar",
  data: {
    labels: ["Red", "Blue"],
    datasets: [
      {
        data: [0, 0],
        backgroundColor: ["rgba(251,113,133,0.7)", "rgba(56,189,248,0.7)"],
        borderRadius: 6,
      },
    ],
  },
  options: {
    plugins: { legend: { display: false } },
    scales: {
      y: { beginAtZero: true, ticks: { color: "#64748b" }, grid: { color: "#1e293b" } },
      x: { ticks: { color: "#94a3b8" }, grid: { display: false } },
    },
  },
});

function setConnected(connected) {
  el("conn-dot").className =
    "h-2 w-2 rounded-full " + (connected ? "bg-emerald-500" : "bg-rose-500");
  el("conn-text").textContent = connected ? "connected" : "disconnected";
}

function renderScores(scores) {
  el("score-red").textContent = scores.red;
  el("score-blue").textContent = scores.blue;
  chart.data.datasets[0].data = [scores.red, scores.blue];
  chart.update();
}

function renderMitigations(mitigations) {
  const wrap = el("mitigations");
  wrap.innerHTML = "";
  for (const [vector, patched] of Object.entries(mitigations)) {
    const chip = document.createElement("span");
    chip.textContent = vector;
    chip.className =
      "rounded-full px-2 py-0.5 text-xs " +
      (patched
        ? "bg-emerald-500/20 text-emerald-300"
        : "bg-rose-500/20 text-rose-300");
    wrap.appendChild(chip);
  }
}

function renderVectorTally() {
  el("vector-tally").innerHTML = Object.entries(vectorCounts)
    .map(
      ([v, n]) =>
        `<div class="flex justify-between"><span>${v}</span><span class="text-slate-500">${n}</span></div>`
    )
    .join("");
}

function pushEvent(event) {
  const colors = { red: "text-rose-400", blue: "text-sky-400" };
  const li = document.createElement("li");
  const time = new Date(event.ts).toLocaleTimeString();
  const detail = event.vector || (event.vectors || []).join(",") || event.ip || "";
  li.className = colors[event.team] || "text-slate-400";
  li.textContent = `${time}  [${event.team || "sys"}] ${event.kind} ${detail}`;
  const feed = el("feed");
  feed.prepend(li);
  while (feed.childElementCount > 60) feed.lastChild.remove();

  for (const v of event.vectors || (event.vector ? [event.vector] : [])) {
    if (v in vectorCounts) vectorCounts[v] += 1;
  }
  renderVectorTally();
}

socket.on("connect", () => setConnected(true));
socket.on("disconnect", () => setConnected(false));

socket.on("snapshot", (snap) => {
  renderScores(snap.scores);
  renderMitigations(snap.mitigations);
  el("uptime").textContent = `${snap.uptime}%`;
  snap.events.forEach(pushEvent);
});

socket.on("scores", renderScores);
socket.on("mitigations", renderMitigations);
socket.on("sla", (data) => (el("uptime").textContent = `${data.uptime}%`));
socket.on("event", pushEvent);

renderVectorTally();
