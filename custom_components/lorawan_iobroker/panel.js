const SELECTED_SOURCE_STORAGE_KEY = "lorawan_iobroker_selected_source";

class LoRaWANIobrokerPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this.data = null;
    this.selectedSource = loadSelectedSource();
    this.search = "";
    this.integration = "";
    this.loading = true;
    this.savingOptions = false;
    this.publishing = false;
  }

  set hass(hass) {
    this._hass = hass;
    if (!this.data && !this._loadingPromise) {
      this.refresh();
    }
  }

  connectedCallback() {
    this.render();
  }

  async refresh() {
    if (!this._hass) return;
    this.loading = true;
    this.render();
    this._loadingPromise = this._hass.callApi("GET", "lorawan_iobroker/data");
    try {
      this.data = await this._loadingPromise;
      if (
        this.data.sources.length &&
        !this.data.sources.some((source) => source.entry_id === this.selectedSource)
      ) {
        this.selectedSource = this.data.sources[0].entry_id;
        saveSelectedSource(this.selectedSource);
      } else if (!this.data.sources.length) {
        this.selectedSource = "";
      }
    } finally {
      this.loading = false;
      this._loadingPromise = null;
      this.render();
    }
  }

  source() {
    const sources = this.data?.sources || [];
    return sources.find((source) => source.entry_id === this.selectedSource) || sources[0];
  }

  devices() {
    const source = this.source();
    if (!source) return [];
    const text = this.search.trim().toLowerCase();
    return source.devices.filter((device) => {
      const matchesIntegration = !this.integration || (device.integrations || []).includes(this.integration);
      const haystack = [
        device.name,
        device.manufacturer,
        device.model,
        ...(device.integrations || []),
        ...(device.labels || []),
        ...(device.domains || []),
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      return matchesIntegration && (!text || haystack.includes(text));
    });
  }

  integrations() {
    const source = this.source();
    if (!source) return [];
    return [...new Set(source.devices.flatMap((device) => device.integrations || []))].sort();
  }

  async saveInterval(value) {
    const source = this.source();
    if (!source || !this._hass) return;
    const interval = Number.parseInt(value, 10);
    if (!Number.isFinite(interval) || interval < 1 || interval > 1440) {
      this.render();
      return;
    }
    this.savingOptions = true;
    this.render();
    try {
      await this._hass.callApi("POST", "lorawan_iobroker/options", {
        entry_id: source.entry_id,
        periodic_interval_minutes: interval,
      });
      source.periodic_interval_minutes = interval;
    } finally {
      this.savingOptions = false;
      this.render();
    }
  }

  async publishNow() {
    const source = this.source();
    if (!source || !this._hass) return;
    this.publishing = true;
    this.render();
    try {
      await this._hass.callApi("POST", "lorawan_iobroker/publish", {
        entry_id: source.entry_id,
      });
    } finally {
      this.publishing = false;
      this.render();
    }
  }

  renderDevice(device) {
    const primary = primaryIntegration(device);

    return `<a class="device-card" href="/config/devices/device/${escapeAttr(device.id)}">
      <div class="logo ${integrationClass(primary)}">
        <img class="brand-icon" src="${escapeAttr(brandIcon(primary))}" data-alt-src="${escapeAttr(brandIcon(primary, true))}" alt="" loading="lazy" />
        <ha-icon class="fallback-icon" icon="${escapeAttr(integrationIcon(primary))}"></ha-icon>
      </div>
      <div class="device-main">
        <div class="device-title">${escapeHtml(device.name)}</div>
      </div>
      <ha-icon class="open" icon="mdi:open-in-new"></ha-icon>
    </a>`;
  }

  render() {
    if (!this.shadowRoot) return;
    const source = this.source();
    const devices = this.devices();
    const integrations = this.integrations();
    const sources = this.data?.sources || [];

    this.shadowRoot.innerHTML = `<style>${styles}</style>
      <main>
        <header>
          <div>
            <h1>ioBroker LoRaWAN</h1>
            <p>${source ? escapeHtml(source.source) : "Keine Quelle eingerichtet"}</p>
          </div>
          <button class="primary" id="refresh">Aktualisieren</button>
        </header>

        <section class="toolbar">
          <select id="source">
            ${sources
              .map(
                (item) =>
                  `<option value="${escapeAttr(item.entry_id)}" ${item.entry_id === this.selectedSource ? "selected" : ""}>${escapeHtml(item.title)} (${escapeHtml(item.source)})</option>`
              )
              .join("")}
          </select>
          <input id="search" type="search" placeholder="Geräte suchen..." value="${escapeAttr(this.search)}" />
          <select id="integration">
            <option value="">Alle Integrationen</option>
            ${integrations
              .map((integration) => `<option value="${escapeAttr(integration)}" ${integration === this.integration ? "selected" : ""}>${escapeHtml(formatIntegration(integration))}</option>`)
              .join("")}
          </select>
          <label class="interval">
            <span title="Periodisches Discovern der mit dem Label versehenen Entities">Discovery-Periode (min)</span>
            <input id="interval" type="number" min="1" max="1440" step="1" value="${escapeAttr(source?.periodic_interval_minutes || 10)}" ${!source || this.savingOptions ? "disabled" : ""} />
          </label>
          <button id="publish" ${!source || this.publishing ? "disabled" : ""}>${this.publishing ? "Sendet..." : "Jetzt senden"}</button>
        </section>

        ${this.loading ? `<div class="notice">Lade Home-Assistant-Geräte...</div>` : ""}
        ${!this.loading && !source ? `<div class="notice">Lege zuerst eine Quelle in den Integrationseinstellungen an.</div>` : ""}
        ${!this.loading && source && !devices.length ? `<div class="notice">Keine passenden Geräte für diese Quelle oder das Label gefunden.</div>` : ""}

        <div class="grid">${devices.map((device) => this.renderDevice(device)).join("")}</div>
      </main>`;

    this.bindEvents();
  }

  bindEvents() {
    this.shadowRoot.getElementById("refresh")?.addEventListener("click", () => this.refresh());
    this.shadowRoot.getElementById("source")?.addEventListener("change", (event) => {
      this.selectedSource = event.target.value;
      saveSelectedSource(this.selectedSource);
      this.integration = "";
      this.render();
    });
    this.shadowRoot.getElementById("search")?.addEventListener("change", (event) => {
      this.search = event.target.value;
      this.render();
    });
    this.shadowRoot.getElementById("integration")?.addEventListener("change", (event) => {
      this.integration = event.target.value;
      this.render();
    });
    this.shadowRoot.getElementById("interval")?.addEventListener("change", (event) => {
      this.saveInterval(event.target.value);
    });
    this.shadowRoot.getElementById("publish")?.addEventListener("click", () => this.publishNow());
    this.shadowRoot.querySelectorAll(".brand-icon").forEach((node) => {
      node.addEventListener("error", () => {
        if (!node.dataset.triedAlt && node.dataset.altSrc) {
          node.dataset.triedAlt = "1";
          node.src = node.dataset.altSrc;
          return;
        }
        node.style.display = "none";
        node.nextElementSibling.style.display = "block";
      });
    });
  }
}

function loadSelectedSource() {
  try {
    return localStorage.getItem(SELECTED_SOURCE_STORAGE_KEY) || "";
  } catch (_err) {
    return "";
  }
}

function saveSelectedSource(entryId) {
  try {
    if (entryId) {
      localStorage.setItem(SELECTED_SOURCE_STORAGE_KEY, entryId);
    } else {
      localStorage.removeItem(SELECTED_SOURCE_STORAGE_KEY);
    }
  } catch (_err) {
    // Ignore storage errors, the panel still works without persistence.
  }
}

function primaryIntegration(device) {
  const integrations = device.integrations || [];
  if (integrations.includes("matter")) return "matter";
  if (integrations.includes("mqtt")) return "mqtt";
  return integrations[0] || "device";
}

function integrationIcon(integration) {
  const icons = {
    matter: "mdi:hexagon-multiple",
    mqtt: "mdi:access-point-network",
    esphome: "mdi:chip",
    shelly: "mdi:power-plug",
    zha: "mdi:zigbee",
    zwave_js: "mdi:z-wave",
  };
  return icons[integration] || "mdi:devices";
}

function brandIcon(integration, alternate = false) {
  const domain = encodeURIComponent(integration || "homeassistant");
  return alternate
    ? `https://brands.home-assistant.io/_/${domain}/icon.png`
    : `https://brands.home-assistant.io/${domain}/icon.png`;
}

function integrationClass(integration) {
  return `integration-${String(integration || "device").replaceAll("_", "-")}`;
}

function formatIntegration(integration) {
  const names = {
    matter: "Matter",
    mqtt: "MQTT",
    esphome: "ESPHome",
    shelly: "Shelly",
    zha: "ZHA",
    zwave_js: "Z-Wave JS",
  };
  return names[integration] || integration;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function escapeAttr(value) {
  return escapeHtml(value);
}

const styles = `
  :host {
    display: block;
    color: var(--primary-text-color);
    background: var(--primary-background-color);
  }
  main {
    padding: 20px;
    max-width: 1280px;
    margin: 0 auto;
  }
  header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    margin-bottom: 16px;
  }
  h1 {
    margin: 0;
    font-size: 28px;
    font-weight: 600;
  }
  p {
    margin: 4px 0 0;
    color: var(--secondary-text-color);
  }
  .toolbar {
    display: grid;
    grid-template-columns: 240px minmax(220px, 1fr) 220px 190px 140px;
    gap: 12px;
    padding: 16px;
    border: 1px solid var(--divider-color);
    border-radius: 8px;
    background: var(--card-background-color);
    margin-bottom: 16px;
  }
  input,
  select,
  button {
    min-height: 40px;
    border: 1px solid var(--divider-color);
    border-radius: 6px;
    padding: 0 12px;
    background: var(--card-background-color);
    color: var(--primary-text-color);
    font: inherit;
  }
  .interval {
    display: grid;
    grid-template-columns: auto minmax(72px, 1fr);
    align-items: center;
    gap: 8px;
    min-width: 0;
  }
  .interval span {
    color: var(--secondary-text-color);
    font-size: 13px;
  }
  .interval input {
    width: 100%;
    min-width: 0;
  }
  button {
    cursor: pointer;
  }
  button:disabled,
  input:disabled {
    cursor: default;
    opacity: 0.65;
  }
  .primary {
    color: var(--text-primary-color, white);
    background: var(--primary-color);
    border-color: var(--primary-color);
  }
  .notice {
    padding: 18px;
    border-radius: 8px;
    background: var(--card-background-color);
    border: 1px solid var(--divider-color);
  }
  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: 12px;
  }
  .device-card {
    display: grid;
    grid-template-columns: 48px minmax(0, 1fr) 24px;
    align-items: center;
    gap: 12px;
    min-width: 0;
    padding: 14px;
    border: 1px solid var(--divider-color);
    border-radius: 8px;
    background: var(--card-background-color);
    color: var(--primary-text-color);
    text-decoration: none;
  }
  .device-card:hover {
    border-color: var(--primary-color);
  }
  .logo {
    position: relative;
    width: 44px;
    height: 44px;
    border-radius: 8px;
    display: grid;
    place-items: center;
    background: #e8f5e9;
    color: #2e7d32;
  }
  .logo img {
    width: 32px;
    height: 32px;
    object-fit: contain;
  }
  .logo .fallback-icon {
    display: none;
    width: 26px;
    height: 26px;
  }
  .device-main {
    min-width: 0;
  }
  .device-title {
    font-size: 16px;
    font-weight: 600;
    overflow-wrap: anywhere;
  }
  .open {
    color: var(--secondary-text-color);
  }
  .integration-mqtt {
    background: #e3f2fd;
    color: #1e88e5;
  }
  .integration-matter {
    background: #e8f5e9;
    color: #2e7d32;
  }
  .integration-esphome {
    background: #ede7f6;
    color: #5e35b1;
  }
  .integration-shelly {
    background: #fff3e0;
    color: #fb8c00;
  }
  .integration-zha,
  .integration-zwave-js {
    background: #f3e5f5;
    color: #8e24aa;
  }
  @media (max-width: 760px) {
    main {
      padding: 12px;
    }
    header,
    .toolbar {
      grid-template-columns: 1fr;
    }
    header {
      align-items: stretch;
    }
    .grid {
      grid-template-columns: 1fr;
    }
  }
`;

if (!customElements.get("lorawan-iobroker-panel")) {
  customElements.define("lorawan-iobroker-panel", LoRaWANIobrokerPanel);
}
