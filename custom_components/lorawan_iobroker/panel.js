const SELECTED_SOURCE_STORAGE_KEY = "lorawan_iobroker_selected_source";

// Keep data in memory for this authenticated connection, never in browser storage.
const panelSessions = new WeakMap();

class LoRaWANIobrokerPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this.data = null;
    this.selectedSource = loadSelectedSource();
    this.view = "devices";
    this.search = "";
    this.integration = "";
    this.loading = true;
    this.savingOptions = false;
    this.publishing = false;
  }

  set hass(hass) {
    const changed = this._connection !== hass.connection || this._userId !== hass.user?.id;
    this._hass = hass;
    if (changed) {
      this._connection = hass.connection;
      this._userId = hass.user?.id;
      let session = panelSessions.get(this._connection);
      if (!session || session.userId !== this._userId) {
        session = { userId: this._userId, data: null, view: "devices", search: "", integration: "" };
        panelSessions.set(this._connection, session);
      }
      this._session = session;
      this.data = session.data;
      this.view = session.view;
      this.search = session.search;
      this.integration = session.integration;
      this.selectedSource = session.selectedSource || loadSelectedSource();
      this.refresh();
    }
  }

  connectedCallback() {
    this.render();
    if (this._hass) this.refresh();
  }

  async refresh() {
    if (!this._hass || this._loadingPromise) return;
    const session = this._session;
    this.loading = true;
    this.error = "";
    this.render();
    try {
      const pending = this._hass.callApi("GET", "lorawan_iobroker/data");
      this._loadingPromise = pending;
      const data = await pending;
      if (session !== this._session) return;
      this.data = data;
      if (
        this.data.sources.length &&
        !this.data.sources.some((source) => source.entry_id === this.selectedSource)
      ) {
        this.selectedSource = this.data.sources[0].entry_id;
        saveSelectedSource(this.selectedSource);
      } else if (!this.data.sources.length) {
        this.selectedSource = "";
      }
    } catch (err) {
      if (session !== this._session) return;
      if (err.status_code === 401 || err.status_code === 403) {
        this.data = null;
        session.data = null;
      }
      this.error = "Gerätedaten konnten nicht geladen werden. Bitte erneut aktualisieren.";
    } finally {
      this._loadingPromise = null;
      if (session === this._session) {
        this.loading = false;
        this.render();
      } else {
        this.refresh();
      }
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

  renderFlowDevice(device, integration = "device") {
    const labelInfo = device.label_on_device
      ? "Gerät gelabelt"
      : device.labeled_entity_count
        ? `${device.labeled_entity_count}/${device.entity_count} Entitäten gelabelt`
        : `${device.entity_count} Entitäten`;
    return `<a class="flow-device ${device.flow === "both" ? "loop-device" : ""}" href="/config/devices/device/${escapeAttr(device.id)}" title="${escapeAttr(labelInfo)}">
      <span class="tiny-logo ${integrationClass(integration)}">
        <img class="brand-icon" src="${escapeAttr(brandIcon(integration))}" data-alt-src="${escapeAttr(brandIcon(integration, true))}" alt="" loading="lazy" />
        <ha-icon class="fallback-icon" icon="${escapeAttr(integrationIcon(integration))}"></ha-icon>
      </span>
      <span class="flow-device-name">${escapeHtml(device.name)}</span>
      ${device.flow === "both" ? `<ha-icon class="loop-icon" icon="mdi:alert-outline" title="Importiertes Gerät besitzt auch das Exportlabel"></ha-icon>` : ""}
    </a>`;
  }

  renderDataFlow(source, devices) {
    const inbound = devices.filter((device) => device.source_match);
    const outbound = devices.filter((device) => device.label_match);
    const loops = outbound.filter((device) => device.source_match);
    const groups = new Map();
    outbound.forEach((device) => {
      const integrations = device.integrations?.length ? device.integrations : ["device"];
      integrations.forEach((integration) => {
        if (!groups.has(integration)) groups.set(integration, []);
        groups.get(integration).push(device);
      });
    });
    const groupEntries = [...groups.entries()].sort(([a], [b]) => a.localeCompare(b));

    return `<section class="flow-section">
      <div class="flow-head">
        <div><h2>Datenfluss</h2><p>Import aus ioBroker und Export aus Home Assistant auf einen Blick</p></div>
        <div class="flow-legend"><span><i class="dot import"></i>Import</span><span><i class="dot export"></i>Export</span></div>
      </div>
      ${loops.length ? `<div class="loop-warning"><ha-icon icon="mdi:alert-outline"></ha-icon><span><strong>${loops.length} mögliche ${loops.length === 1 ? "Rückkopplung" : "Rückkopplungen"}:</strong> Importierte Geräte besitzen auch das Label „${escapeHtml(source.label)}“: ${loops.map((device) => `<a href="/config/devices/device/${escapeAttr(device.id)}">${escapeHtml(device.name)}</a>`).join(", ")}.</span></div>` : ""}
      <div class="flow-map">
        <div class="flow-column source-column">
          <div class="column-caption">Import aus ioBroker</div>
          <article class="flow-node source-node">
            <div class="node-icon"><ha-icon icon="mdi:server-network"></ha-icon></div>
            <div><span class="eyebrow">ioBroker-Quelle</span><strong>${escapeHtml(source.source)}</strong><small>${inbound.length} Geräte · ${inbound.reduce((sum, d) => sum + d.entity_count, 0)} Entitäten</small></div>
          </article>
          <details class="device-list" ${inbound.length <= 8 ? "open" : ""}>
            <summary><ha-icon icon="mdi:magnify"></ha-icon><span>${inbound.length} importierte Geräte anzeigen</span></summary>
            <div>${inbound.length ? inbound.map((device) => this.renderFlowDevice(device, "mqtt")).join("") : `<span class="empty-small">Keine über diese Quelle erkannten Geräte</span>`}</div>
          </details>
        </div>

        <div class="flow-link transport import-link"><span>MQTT Discovery</span><i></i></div>

        <div class="flow-column mqtt-column">
          <div class="column-caption">Transport</div>
          <article class="flow-node mqtt-node">
            <div class="node-icon integration-mqtt"><img class="brand-icon" src="${brandIcon("mqtt")}" data-alt-src="${brandIcon("mqtt", true)}" alt=""/><ha-icon class="fallback-icon" icon="mdi:access-point-network"></ha-icon></div>
            <div><span class="eyebrow">Transport</span><strong>MQTT-Broker</strong><small>Discovery &amp; Export</small></div>
          </article>
        </div>

        <div class="flow-link transport dual-link"><span class="import-label">Import</span><i></i><span class="export-label">Export</span></div>

        <div class="flow-column ha-column">
          <div class="column-caption">Zentrale</div>
          <article class="ha-node">
            <img src="/static/icons/favicon-192x192.png" alt="Home Assistant" />
            <strong>Home Assistant</strong>
            <small>${outbound.length} Geräte zum Export</small>
            <span class="label-badge"><ha-icon icon="mdi:label-outline"></ha-icon>${escapeHtml(source.label)}</span>
          </article>
        </div>

        <div class="flow-link branch-link"><span>über Label</span><i></i></div>

        <div class="flow-column integrations-column">
          <div class="column-caption">Export nach ioBroker</div>
          <div class="integration-groups">
            ${groupEntries.length ? groupEntries.map(([integration, items]) => `<details class="integration-group" open>
              <summary>
                <span class="group-logo ${integrationClass(integration)}"><img class="brand-icon" src="${escapeAttr(brandIcon(integration))}" data-alt-src="${escapeAttr(brandIcon(integration, true))}" alt=""/><ha-icon class="fallback-icon" icon="${escapeAttr(integrationIcon(integration))}"></ha-icon></span>
                <strong>${escapeHtml(formatIntegration(integration))}</strong><span class="count">${items.length}</span>
              </summary>
              <div class="group-devices">${items.map((device) => this.renderFlowDevice(device, integration)).join("")}</div>
            </details>`).join("") : `<div class="notice">Keine Geräte mit dem Label „${escapeHtml(source.label)}“ gefunden.</div>`}
          </div>
        </div>
      </div>
    </section>`;
  }

  render() {
    if (!this.shadowRoot) return;
    if (this._session) {
      Object.assign(this._session, {
        data: this.data, selectedSource: this.selectedSource,
        view: this.view, search: this.search, integration: this.integration,
      });
    }
    const source = this.source();
    const devices = this.devices();
    const integrations = this.integrations();
    const sources = this.data?.sources || [];

    this.shadowRoot.innerHTML = `<style>${styles}</style>
      <main>
        <header>
          <div>
            <h1>ioBroker LoRaWAN</h1>
            <p>${source ? escapeHtml(source.source) : (!this.data ? (this.error ? "Daten nicht verfügbar" : "Quellen werden geladen…") : "Keine Quelle eingerichtet")}</p>
          </div>
          <div class="header-actions">
            <nav class="view-tabs" aria-label="Ansicht">
              <button id="view-devices" class="${this.view === "devices" ? "active" : ""}"><ha-icon icon="mdi:view-grid-outline"></ha-icon>Geräte</button>
              <button id="view-flow" class="${this.view === "flow" ? "active" : ""}"><ha-icon icon="mdi:transit-connection-variant"></ha-icon>Datenfluss</button>
            </nav>
            <button class="primary" id="refresh" ${this.loading ? "disabled" : ""}>${this.loading ? "Aktualisiere…" : "Aktualisieren"}</button>
          </div>
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

        ${this.loading && !this.data ? `<div class="notice">Lade Home-Assistant-Geräte...</div>` : ""}
        ${this.error ? `<div class="notice" role="alert">${escapeHtml(this.error)}</div>` : ""}
        ${this.data && !source ? `<div class="notice">Lege zuerst eine Quelle in den Integrationseinstellungen an.</div>` : ""}
        ${source && !devices.length ? `<div class="notice">Keine passenden Geräte für diese Quelle oder das Label gefunden.</div>` : ""}

        ${source ? (this.view === "flow" ? this.renderDataFlow(source, devices) : `<div class="grid">${devices.map((device) => this.renderDevice(device)).join("")}</div>`) : ""}
      </main>`;

    this.bindEvents();
  }

  bindEvents() {
    this.shadowRoot.getElementById("refresh")?.addEventListener("click", () => this.refresh());
    this.shadowRoot.getElementById("view-devices")?.addEventListener("click", () => { this.view = "devices"; this.render(); });
    this.shadowRoot.getElementById("view-flow")?.addEventListener("click", () => { this.view = "flow"; this.render(); });
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
  .header-actions,
  .view-tabs,
  .flow-head,
  .flow-legend {
    display: flex;
    align-items: center;
  }
  .header-actions { gap: 12px; }
  .view-tabs {
    padding: 3px;
    gap: 2px;
    border-radius: 8px;
    background: var(--secondary-background-color);
  }
  .view-tabs button {
    display: flex;
    align-items: center;
    gap: 7px;
    min-height: 36px;
    border: 0;
    background: transparent;
  }
  .view-tabs button.active {
    background: var(--card-background-color);
    color: var(--primary-color);
    box-shadow: 0 1px 3px rgba(0,0,0,.14);
  }
  .view-tabs ha-icon { --mdc-icon-size: 20px; }
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
  .flow-section {
    margin-top: 22px;
    padding: 20px;
    border: 1px solid var(--divider-color);
    border-radius: 12px;
    background: var(--card-background-color);
    overflow: auto;
  }
  .flow-head { justify-content: space-between; gap: 16px; margin-bottom: 18px; }
  .flow-head h2 { margin: 0; font-size: 22px; }
  .flow-head p { font-size: 13px; }
  .flow-legend { gap: 14px; color: var(--secondary-text-color); font-size: 13px; }
  .dot { display: inline-block; width: 9px; height: 9px; margin-right: 6px; border-radius: 50%; }
  .dot.import { background: #2196f3; }
  .dot.export { background: #43a047; }
  .loop-warning {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 11px 14px;
    margin-bottom: 18px;
    border: 1px solid #f9a825;
    border-radius: 8px;
    color: var(--primary-text-color);
    background: rgba(249,168,37,.12);
    font-size: 13px;
  }
  .loop-warning ha-icon { color: #f9a825; }
  .loop-warning a {
    color: var(--primary-color);
    font-weight: 600;
    text-decoration: none;
  }
  .loop-warning a:hover { text-decoration: underline; }
  .flow-map {
    display: grid;
    grid-template-columns: minmax(210px, 1.1fr) 90px 160px 90px 180px 90px minmax(280px, 1.7fr);
    align-items: start;
    min-width: 1120px;
    padding: 4px 0 12px;
  }
  .flow-column { min-width: 0; }
  .column-caption {
    height: 28px;
    color: var(--secondary-text-color);
    font-size: 11px;
    font-weight: 600;
    letter-spacing: .05em;
    text-transform: uppercase;
  }
  .ha-column .column-caption { text-align: center; transform: translateY(-14px); }
  .flow-node {
    display: flex;
    align-items: center;
    gap: 12px;
    min-height: 76px;
    padding: 13px;
    border: 1px solid var(--divider-color);
    border-radius: 10px;
    background: var(--primary-background-color);
    box-sizing: border-box;
  }
  .source-node { border-left: 4px solid #2196f3; }
  .mqtt-node { border-top: 3px solid #7b1fa2; }
  .flow-node > div:last-child { display: grid; min-width: 0; }
  .flow-node strong { overflow-wrap: anywhere; }
  .flow-node small, .ha-node small { margin-top: 4px; color: var(--secondary-text-color); }
  .eyebrow { color: var(--secondary-text-color); font-size: 10px; text-transform: uppercase; }
  .node-icon {
    flex: 0 0 42px;
    width: 42px;
    height: 42px;
    display: grid;
    place-items: center;
    border-radius: 50%;
    background: rgba(33,150,243,.12);
    color: #1976d2;
  }
  .node-icon img { width: 28px; height: 28px; object-fit: contain; }
  .node-icon .fallback-icon { display: none; }
  .ha-node {
    width: 158px;
    min-height: 128px;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    text-align: center;
    margin: -25px auto 0;
    padding: 12px;
    border: 4px solid rgba(3,169,244,.28);
    border-radius: 50%;
    background: var(--primary-background-color);
    box-shadow: 0 4px 18px rgba(0,0,0,.12);
  }
  .ha-node img { width: 40px; height: 40px; margin-bottom: 4px; }
  .ha-node strong { font-size: 15px; }
  .label-badge {
    display: flex;
    align-items: center;
    gap: 4px;
    max-width: 140px;
    margin-top: 9px;
    padding: 4px 8px;
    border-radius: 999px;
    color: #2e7d32;
    background: rgba(76,175,80,.14);
    font-size: 11px;
    overflow-wrap: anywhere;
  }
  .label-badge ha-icon { --mdc-icon-size: 15px; }
  .flow-link { position: relative; height: 80px; margin-top: 28px; }
  .flow-link i { position: absolute; left: 8px; right: 8px; top: 39px; height: 2px; background: #2196f3; }
  .flow-link i::after {
    content: "";
    position: absolute;
    right: -1px;
    top: -4px;
    border-left: 8px solid #2196f3;
    border-top: 5px solid transparent;
    border-bottom: 5px solid transparent;
  }
  .flow-link > span {
    position: absolute;
    top: 17px;
    left: 0;
    right: 0;
    text-align: center;
    color: var(--secondary-text-color);
    font-size: 10px;
    white-space: nowrap;
  }
  .dual-link i { background: linear-gradient(to bottom, #2196f3 0 50%, #43a047 50%); }
  .dual-link i::before {
    content: "";
    position: absolute;
    left: -1px;
    top: 1px;
    border-right: 8px solid #43a047;
    border-top: 5px solid transparent;
    border-bottom: 5px solid transparent;
  }
  .dual-link .import-label { top: 16px; color: #1976d2; }
  .dual-link .export-label { top: 46px; color: #388e3c; }
  .branch-link i { background: #43a047; }
  .branch-link i::after { display: none; }
  .branch-link i::before {
    content: "";
    position: absolute;
    left: -1px;
    top: -4px;
    border-right: 8px solid #43a047;
    border-top: 5px solid transparent;
    border-bottom: 5px solid transparent;
  }
  .branch-link > span { color: #388e3c; }
  .device-list { margin-top: 10px; }
  .device-list summary,
  .integration-group summary {
    cursor: pointer;
    color: var(--secondary-text-color);
    font-size: 12px;
  }
  .device-list summary {
    display: flex;
    align-items: center;
    gap: 5px;
  }
  .device-list summary ha-icon { --mdc-icon-size: 16px; }
  .device-list > div { display: grid; gap: 6px; margin-top: 8px; max-height: 430px; overflow: auto; }
  .flow-device {
    display: grid;
    grid-template-columns: 28px minmax(0,1fr) auto;
    align-items: center;
    gap: 8px;
    min-height: 38px;
    padding: 5px 8px;
    border: 1px solid var(--divider-color);
    border-radius: 7px;
    color: var(--primary-text-color);
    background: var(--primary-background-color);
    text-decoration: none;
  }
  .flow-device:hover { border-color: var(--primary-color); }
  .flow-device.loop-device { border-color: #f9a825; }
  .flow-device-name { overflow-wrap: anywhere; font-size: 12px; font-weight: 500; }
  .tiny-logo, .group-logo { display: grid; place-items: center; border-radius: 6px; }
  .tiny-logo { width: 28px; height: 28px; }
  .tiny-logo img { width: 20px; height: 20px; object-fit: contain; }
  .tiny-logo .fallback-icon { display: none; --mdc-icon-size: 18px; }
  .loop-icon { color: #f9a825; --mdc-icon-size: 18px; }
  .empty-small { padding: 8px; color: var(--secondary-text-color); font-size: 12px; }
  .integration-groups { display: grid; gap: 10px; }
  .integration-group {
    border: 1px solid var(--divider-color);
    border-radius: 9px;
    background: var(--primary-background-color);
    overflow: hidden;
  }
  .integration-group summary {
    display: grid;
    grid-template-columns: 34px minmax(0,1fr) auto;
    align-items: center;
    gap: 9px;
    padding: 9px 11px;
    list-style: none;
    color: var(--primary-text-color);
  }
  .integration-group summary::-webkit-details-marker { display: none; }
  .group-logo { width: 34px; height: 34px; }
  .group-logo img { width: 24px; height: 24px; object-fit: contain; }
  .group-logo .fallback-icon { display: none; --mdc-icon-size: 21px; }
  .count {
    min-width: 22px;
    padding: 3px 6px;
    border-radius: 999px;
    text-align: center;
    color: var(--secondary-text-color);
    background: var(--secondary-background-color);
    font-size: 11px;
  }
  .group-devices { display: grid; gap: 5px; padding: 0 9px 9px 43px; max-height: 300px; overflow: auto; }
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
    .header-actions { align-items: stretch; flex-direction: column; }
    .view-tabs button { flex: 1; justify-content: center; }
    .grid {
      grid-template-columns: 1fr;
    }
  }
`;

if (!customElements.get("lorawan-iobroker-panel")) {
  customElements.define("lorawan-iobroker-panel", LoRaWANIobrokerPanel);
}
