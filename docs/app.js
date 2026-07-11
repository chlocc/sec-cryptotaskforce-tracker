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

// Lazy rendering: all items stay in memory (filters/search see everything),
// but the DOM only gets BATCH cards at a time, appended as the user scrolls.
const BATCH = 30;
let filtered = [];
let renderedCount = 0;
const sentinel = document.getElementById("sentinel");

function cardHTML(item) {
  return `
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
    </article>`;
}

function render() {
  filtered = DATA.items.filter(matches);
  count.textContent = filtered.length + " item" + (filtered.length === 1 ? "" : "s");
  window.scrollTo(0, 0);  // results restart from the top; also keeps the first batch small
  feed.innerHTML = "";
  renderedCount = 0;
  if (!filtered.length) {
    feed.innerHTML = '<div class="empty">No items match.</div>';
    return;
  }
  appendBatch();
}

function appendBatch() {
  if (renderedCount >= filtered.length) return;
  const next = filtered.slice(renderedCount, renderedCount + BATCH);
  feed.insertAdjacentHTML("beforeend", next.map(cardHTML).join(""));
  renderedCount += next.length;
  // Re-observe so the observer re-evaluates: if the sentinel is still in view
  // (short viewport / few items per screen), the callback fires again.
  observer.unobserve(sentinel);
  observer.observe(sentinel);
  // Short-viewport case: if the batch didn't push the sentinel off-screen,
  // keep filling until the page is scrollable.
  if (nearBottom()) appendBatch();
}

function nearBottom() {
  return window.innerHeight + window.scrollY >= document.body.scrollHeight - 900;
}

const observer = new IntersectionObserver(entries => {
  if (entries.some(e => e.isIntersecting)) appendBatch();
}, { rootMargin: "600px 0px" });  // start loading well before the bottom
observer.observe(sentinel);

// Fallback for environments where IntersectionObserver delivery is unreliable
// (some embedded webviews): plain scroll-position check.
window.addEventListener("scroll", () => { if (nearBottom()) appendBatch(); }, { passive: true });

feed.addEventListener("click", e => {
  const btn = e.target.closest(".topic");
  if (!btn) return;
  activeTopics.add(btn.dataset.topic);
  syncTopicChips();
  render();
  document.getElementById("topic-row").scrollIntoView({ behavior: "smooth", block: "nearest" });
});
