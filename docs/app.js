let DATA = { items: [], source_labels: {}, topics: [] };
let activeSource = "all";
let activeTopics = new Set();
let query = "";

const feed = document.getElementById("feed");
const count = document.getElementById("count");
const topicChips = document.getElementById("topic-chips");
const topicClear = document.getElementById("topic-clear");

fetch("data.json")
  .then(r => r.json())
  .then(data => {
    DATA = data;
    const d = new Date(data.generated_at);
    document.getElementById("updated").textContent =
      "Last updated " + d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }) + ".";
    renderTopicChips();
    render();
  })
  .catch(() => { feed.innerHTML = '<div class="empty">Could not load data.json</div>'; });

function renderTopicChips() {
  topicChips.innerHTML = DATA.topics.map(t => `
    <button class="chip" data-topic="${esc(t)}">${esc(t)}</button>
  `).join("");
}

topicChips.addEventListener("click", e => {
  const btn = e.target.closest(".chip");
  if (!btn) return;
  const t = btn.dataset.topic;
  if (activeTopics.has(t)) activeTopics.delete(t);
  else activeTopics.add(t);
  syncTopicChips();
  render();
});

topicClear.addEventListener("click", () => {
  activeTopics.clear();
  syncTopicChips();
  render();
});

function syncTopicChips() {
  topicChips.querySelectorAll(".chip").forEach(el => {
    el.classList.toggle("active", activeTopics.has(el.dataset.topic));
  });
  topicClear.hidden = activeTopics.size === 0;
}

document.getElementById("tabs").addEventListener("click", e => {
  const btn = e.target.closest(".tab");
  if (!btn) return;
  document.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
  btn.classList.add("active");
  activeSource = btn.dataset.source;
  render();
});

document.getElementById("search").addEventListener("input", e => {
  query = e.target.value.trim().toLowerCase();
  render();
});

function matches(item) {
  if (activeSource !== "all" && item.source !== activeSource) return false;
  if (activeTopics.size > 0 && !item.topics.some(t => activeTopics.has(t))) return false;
  if (!query) return true;
  const hay = [item.title, item.author, item.topics.join(" "), item.key_points.join(" "), item.takeaway]
    .join(" ").toLowerCase();
  return query.split(/\s+/).every(term => hay.includes(term));
}

function fmtDate(iso) {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

function esc(s) {
  const div = document.createElement("div");
  div.textContent = s;
  return div.innerHTML;
}

function render() {
  const items = DATA.items.filter(matches);
  count.textContent = items.length + " item" + (items.length === 1 ? "" : "s");
  if (!items.length) {
    feed.innerHTML = '<div class="empty">No items match.</div>';
    return;
  }
  feed.innerHTML = items.map(item => `
    <article class="card">
      <div class="card-head">
        <span class="badge ${esc(item.source)}">${esc(DATA.source_labels[item.source] || item.source)}</span>
        <span class="date">${fmtDate(item.date)}${item.date_approximate ? " (approx.)" : ""}</span>
        ${item.author ? `<span class="author">· ${esc(item.author)}</span>` : ""}
      </div>
      <h2><a href="${esc(item.url)}" target="_blank" rel="noopener">${esc(item.title)}</a></h2>
      ${item.takeaway ? `<p class="takeaway">${esc(item.takeaway)}</p>` : ""}
      <ul class="points">
        ${item.key_points.map(p => `<li>${esc(p)}</li>`).join("")}
      </ul>
      ${item.thin ? '<div class="thin-note">Automated summary unavailable — see source.</div>' : ""}
      ${item.topics.length ? `<div class="topics">${item.topics.map(t => `<button class="topic" data-topic="${esc(t)}">${esc(t)}</button>`).join("")}</div>` : ""}
    </article>
  `).join("");
}

feed.addEventListener("click", e => {
  const btn = e.target.closest(".topic");
  if (!btn) return;
  activeTopics.add(btn.dataset.topic);
  syncTopicChips();
  render();
  document.getElementById("topic-row").scrollIntoView({ behavior: "smooth", block: "nearest" });
});
