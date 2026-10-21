"use strict";

/* Everything from the index is untrusted media text. It reaches the page only through
   textContent, value and setAttribute on fixed attribute names (spec 40). */

const form = document.getElementById("search");
const assetSelect = document.getElementById("asset");
const statusEl = document.getElementById("status");
const player = document.getElementById("player");
const results = document.getElementById("results");
const names = new Map();
let playerAsset = null;
let searchId = 0;

function hms(t) {
  const cs = Math.floor(t * 100 + 0.5);
  const pad = (n) => String(n).padStart(2, "0");
  return (
    Math.floor(cs / 360000) + ":" + pad(Math.floor(cs / 6000) % 60) + ":" +
    pad(Math.floor(cs / 100) % 60) + "." + pad(cs % 100)
  );
}

function mediaUrl(assetId, startS) {
  return "/media/" + encodeURIComponent(assetId) + "#t=" + startS;
}

function fileName(hit) {
  return names.get(hit.asset_id) || hit.path.split(/[\\/]/).pop();
}

function play(hit) {
  if (playerAsset === hit.asset_id) {
    player.currentTime = hit.start_s;
  } else {
    player.setAttribute("src", mediaUrl(hit.asset_id, hit.start_s));
    playerAsset = hit.asset_id;
  }
  const started = player.play();
  if (started) {
    started.catch(() => {});
  }
}

function renderHit(hit) {
  const li = document.createElement("li");
  const name = fileName(hit);
  const when = hit.modality === "speech"
    ? hms(hit.start_s) + "–" + hms(hit.end_s)
    : hms(hit.start_s);

  const thumb = document.createElement("video");
  thumb.preload = "metadata";
  thumb.muted = true;
  thumb.playsInline = true;
  thumb.setAttribute("aria-hidden", "true");
  thumb.setAttribute("src", mediaUrl(hit.asset_id, hit.start_s));
  li.append(thumb);

  const body = document.createElement("div");
  const button = document.createElement("button");
  button.type = "button";
  button.setAttribute("aria-label", "Play " + name + " at " + when);
  button.textContent = when;
  button.addEventListener("click", () => play(hit));
  const meta = document.createElement("span");
  meta.textContent = " " + hit.modality + " " + hit.score.toFixed(3) + " " + name;
  const head = document.createElement("div");
  head.append(button, meta);
  body.append(head);

  const text = document.createElement("p");
  text.textContent = hit.text;
  body.append(text);

  if (hit.media_text.length > 0) {
    const shown = document.createElement("p");
    shown.setAttribute("class", "untrusted");
    shown.textContent =
      "On-screen text (from the video, untrusted): " +
      hit.media_text.map((s) => '"' + s + '"').join(", ");
    body.append(shown);
  }
  li.append(body);
  return li;
}

async function search(event) {
  event.preventDefault();
  const mine = ++searchId;
  const params = new URLSearchParams({
    q: form.elements.q.value,
    k: "20",
    modality: form.elements.modality.value,
  });
  if (form.elements.asset.value !== "") {
    params.set("asset", form.elements.asset.value);
  }
  statusEl.textContent = "Searching…";
  let response;
  try {
    response = await fetch("/api/search?" + params.toString());
  } catch (err) {
    if (mine === searchId) {
      statusEl.textContent = "Search failed (no response)";
    }
    return;
  }
  if (mine !== searchId) {
    return;
  }
  if (!response.ok) {
    results.replaceChildren();
    statusEl.textContent = "Search failed (HTTP " + response.status + ")";
    return;
  }
  const data = await response.json();
  if (mine !== searchId) {
    return;
  }
  results.replaceChildren(...data.hits.map(renderHit));
  const n = data.hits.length;
  statusEl.textContent = n === 0 ? "No results" : n === 1 ? "1 result" : n + " results";
}

async function loadAssets() {
  try {
    const response = await fetch("/api/assets");
    if (!response.ok) {
      return;
    }
    const data = await response.json();
    for (const asset of data.assets) {
      names.set(asset.asset_id, asset.name);
      const option = document.createElement("option");
      option.value = asset.asset_id;
      option.textContent = asset.name;
      assetSelect.append(option);
    }
  } catch (err) {
    /* the file filter stays at "All files" */
  }
}

form.addEventListener("submit", search);
player.addEventListener("error", () => {
  statusEl.textContent = "This browser can't play this file (container or codec).";
});
loadAssets();
