/* rag_chat.js — AI chat + nearby-psychologist UI */

const chatForm       = document.getElementById("rag-form");
const chatInput      = document.getElementById("rag-input");
const chatSend       = document.getElementById("rag-send");
const chatMessages   = document.getElementById("rag-messages");
const nearbyButton   = document.getElementById("rag-nearby-button");
const locationStatus = document.getElementById("rag-location-status");
const providerList   = document.getElementById("rag-provider-list");
const mapSearch      = document.getElementById("rag-map-search");

// Always use relative URLs — works on localhost:8000 and on any deployed host (Render, etc.)
const ragApiBase = "";

// ── API helper ────────────────────────────────────────────────────────────

async function requestRagApi(path, options) {
  let response;
  try {
    response = await fetch(`${ragApiBase}${path}`, options);
  } catch {
    throw new Error(
      "Cannot reach the chatbot server. " +
      "If running locally, start it with: uvicorn rag_engine:app --host 127.0.0.1 --port 8000 " +
      "then open http://127.0.0.1:8000. If deployed, check that the server is running.",
    );
  }

  if (!response.headers.get("content-type")?.includes("application/json")) {
    throw new Error(
      "The request reached a web page instead of the chatbot API. " +
      "Make sure you are opening the app via the server URL, not the HTML file directly.",
    );
  }

  const result = await response.json();
  if (!response.ok) {
    throw new Error(result.detail || "The chatbot service could not complete the request.");
  }
  return result;
}

// ── Message rendering ─────────────────────────────────────────────────────

function addMessage(text, className, sources = [], urgent = false) {
  const bubble = document.createElement("div");
  bubble.className = `rag-message ${className}${urgent ? " rag-urgent" : ""}`;

  const content = document.createElement("p");
  content.className = "rag-bubble-text";
  content.textContent = text;
  bubble.append(content);

  if (sources.length) {
    const heading = document.createElement("p");
    heading.className = "rag-sources-label";
    heading.textContent = "Sources";
    bubble.append(heading);

    const list = document.createElement("ul");
    list.className = "rag-sources";
    for (const source of sources) {
      const item = document.createElement("li");
      const link = document.createElement("a");
      link.href = source.url;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.textContent = source.title || source.url;
      item.append(link);
      list.append(item);
    }
    bubble.append(list);
  }

  chatMessages.append(bubble);
  chatMessages.scrollTop = chatMessages.scrollHeight;
  return bubble;
}

function addTypingIndicator() {
  const bubble = document.createElement("div");
  bubble.className = "rag-message rag-assistant rag-typing";
  bubble.id = "rag-typing-indicator";
  bubble.setAttribute("aria-label", "Assistant is typing");
  bubble.innerHTML = '<span></span><span></span><span></span>';
  chatMessages.append(bubble);
  chatMessages.scrollTop = chatMessages.scrollHeight;
  return bubble;
}

function removeTypingIndicator() {
  document.getElementById("rag-typing-indicator")?.remove();
}

// ── Chat submit ───────────────────────────────────────────────────────────

chatForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = chatInput.value.trim();
  if (!message) return;

  addMessage(message, "rag-user");
  chatInput.value = "";
  chatInput.style.height = "auto";
  chatSend.disabled = true;
  chatSend.textContent = "…";

  const typingBubble = addTypingIndicator();

  try {
    const result = await requestRagApi("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message }),
    });
    removeTypingIndicator();
    addMessage(result.answer, "rag-assistant", result.sources ?? [], result.urgent ?? false);
  } catch (error) {
    removeTypingIndicator();
    addMessage(error.message, "rag-assistant rag-error");
  } finally {
    chatSend.disabled = false;
    chatSend.textContent = "Ask";
    chatInput.focus();
  }
});

// Auto-grow textarea
chatInput.addEventListener("input", () => {
  chatInput.style.height = "auto";
  chatInput.style.height = `${Math.min(chatInput.scrollHeight, 160)}px`;
});

// ── Nearby providers ──────────────────────────────────────────────────────

function showProviderResults(providers) {
  providerList.replaceChildren();

  if (!providers.length) {
    locationStatus.textContent =
      "No named providers were found nearby. Try the OpenStreetMap link or contact a local health service.";
    return;
  }

  locationStatus.textContent =
    `Found ${providers.length} listed provider${providers.length === 1 ? "" : "s"} within the search area. Confirm availability directly.`;

  for (const p of providers) {
    const item = document.createElement("li");
    item.className = "rag-provider-card";

    const nameEl = document.createElement("a");
    nameEl.className = "rag-provider-name";
    nameEl.href = p.map_url;
    nameEl.target = "_blank";
    nameEl.rel = "noopener noreferrer";
    nameEl.textContent = p.name;

    const meta = document.createElement("p");
    meta.className = "rag-provider-meta";
    const dist = `${p.distance_km} km away`;
    const type = p.type || "Health service";
    meta.textContent = `${type} · ${dist}`;

    item.append(nameEl, meta);

    if (p.address) {
      const addr = document.createElement("p");
      addr.className = "rag-provider-address";
      addr.textContent = `📍 ${p.address}`;
      item.append(addr);
    }

    const links = document.createElement("div");
    links.className = "rag-provider-links";

    if (p.phone) {
      const tel = document.createElement("a");
      tel.href = `tel:${p.phone.replace(/\s/g, "")}`;
      tel.textContent = `📞 ${p.phone}`;
      links.append(tel);
    }

    if (p.website) {
      const web = document.createElement("a");
      web.href = p.website.startsWith("http") ? p.website : `https://${p.website}`;
      web.target = "_blank";
      web.rel = "noopener noreferrer";
      web.textContent = "🌐 Website";
      links.append(web);
    }

    const mapLink = document.createElement("a");
    mapLink.href = p.map_url;
    mapLink.target = "_blank";
    mapLink.rel = "noopener noreferrer";
    mapLink.textContent = "🗺 View on map";
    links.append(mapLink);

    if (links.children.length) item.append(links);

    providerList.append(item);
  }
}

nearbyButton.addEventListener("click", () => {
  providerList.replaceChildren();

  if (!navigator.geolocation) {
    locationStatus.textContent =
      "Location sharing is not available in this browser. Use the OpenStreetMap link to search manually.";
    return;
  }

  nearbyButton.disabled = true;
  locationStatus.textContent = "Waiting for location permission…";

  navigator.geolocation.getCurrentPosition(
    async ({ coords }) => {
      const { latitude, longitude } = coords;
      mapSearch.href = `https://www.openstreetmap.org/#map=13/${latitude}/${longitude}`;
      mapSearch.hidden = false;
      locationStatus.textContent = "Searching nearby psychologists and clinics…";

      try {
        const result = await requestRagApi("/api/doctors", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ latitude, longitude }),
        });
        showProviderResults(result.providers);
      } catch (error) {
        locationStatus.textContent = error.message;
      } finally {
        nearbyButton.disabled = false;
      }
    },
    (error) => {
      const messages = {
        1: "Location permission was denied. Allow location access in your browser settings.",
        2: "Your location could not be determined. Try again.",
        3: "Location lookup timed out. Try again.",
      };
      locationStatus.textContent =
        messages[error.code] || "Location lookup failed. Try again or use OpenStreetMap search.";
      nearbyButton.disabled = false;
    },
    { enableHighAccuracy: false, timeout: 15000, maximumAge: 300000 },
  );
});
