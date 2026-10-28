/* Native Home Assistant custom panel. No external scripts or build step. */
class StatefulScenesRevisitedPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this.data = { scenes: [], brightness_tolerance: 3 };
    this.selected = null;
    this.generation = 0;
    this.shadowRoot.innerHTML = `
      <style>
        :host { display:block; color:var(--primary-text-color,#202a35); background:var(--primary-background-color,#f5f7fa); min-height:100%; font:16px/1.5 var(--paper-font-body1_-_font-family,system-ui); }
        * { box-sizing:border-box; } main { max-width:1280px; margin:auto; padding:28px; }
        header { display:flex; gap:12px; align-items:center; } h1 { font-size:28px; margin:0; } h2 { font-size:19px; margin:0 0 16px; }
        p { color:var(--secondary-text-color,#56616c); } .workspace { margin-top:24px; }
        [role=tablist] { display:flex; gap:8px; border-bottom:1px solid var(--divider-color,#dce1e7); margin-bottom:22px; }
        [role=tab] { margin:0; padding:12px 16px; border-radius:8px 8px 0 0; border-bottom:3px solid transparent; background:transparent; color:var(--secondary-text-color,#56616c); }
        [role=tab][aria-selected=true] { border-bottom-color:var(--primary-color,#176b91); color:var(--primary-color,#176b91); font-weight:600; }
        :focus-visible { outline:2px solid var(--primary-color,#176b91); outline-offset:3px; }
        section { border:1px solid var(--divider-color,#dce1e7); border-radius:16px; padding:22px; background:var(--card-background-color,white); margin-bottom:20px; }
        label { display:block; margin:14px 0 5px; } input,select,button,textarea { font:inherit; }
        input[type=number],input[type=text],input[type=search],select,textarea { width:100%; padding:10px; border:1px solid var(--divider-color,#bac3cd); border-radius:7px; background:var(--card-background-color,white); color:inherit; }
        textarea { resize:vertical; }
        button { cursor:pointer; border:0; border-radius:8px; padding:10px 16px; margin-top:16px; color:var(--text-primary-color,white); background:var(--primary-color,#176b91); }
        button:disabled { opacity:.5; cursor:default; } .menu { margin:0; padding:8px; background:transparent; color:inherit; font-size:24px; }
        small { color:var(--secondary-text-color,#56616c); display:block; margin:6px 0; } .check { display:flex; align-items:center; gap:8px; }
        fieldset { min-width:0; margin:16px 0 0; padding:0; border:0; } legend { padding:0; } .check { overflow-wrap:anywhere; } .check input { flex-shrink:0; } fieldset:disabled { opacity:.6; }
        #status { font-weight:600; padding:12px; background:var(--secondary-background-color,#edf3f6); border-radius:8px; margin:16px 0; }
        .switch-details { display:flex; flex-wrap:wrap; align-items:center; gap:8px; margin:-6px 0 20px; }
        .switch-details code { overflow-wrap:anywhere; min-width:0; } .switch-details button { margin:0; padding:6px 10px; }
        #switch-state { display:inline-flex; align-items:center; gap:10px; margin-left:auto; flex-shrink:0; color:var(--secondary-text-color,#56616c); }
        #switch-state::after { content:""; width:40px; height:24px; border-radius:12px; background:var(--secondary-text-color,#56616c); background-image:radial-gradient(circle at 12px 12px,var(--card-background-color,white) 8px,transparent 9px); }
        #switch-state.is-on { color:var(--primary-color,#176b91); }
        #switch-state.is-on::after { background-color:var(--primary-color,#176b91); background-image:radial-gradient(circle at 28px 12px,var(--card-background-color,white) 8px,transparent 9px); }
        #switch-state.is-indeterminate::after { opacity:.45; background-image:radial-gradient(circle at 20px 12px,var(--card-background-color,white) 8px,transparent 9px); }
        .table { overflow:auto; } table { width:100%; border-collapse:collapse; font-size:14px; } th,td { text-align:left; vertical-align:top; padding:10px 8px; border-bottom:1px solid var(--divider-color,#ddd); } td { overflow-wrap:anywhere; max-width:280px; } th { white-space:nowrap; }
        #diff tr.is-match { background:color-mix(in srgb,var(--success-color,#43a047) 18%,var(--card-background-color,white)); }
        #diff tr.is-mismatch { background:color-mix(in srgb,var(--error-color,#db4437) 18%,var(--card-background-color,white)); }
        .scene-layout { display:grid; grid-template-columns:280px minmax(0,1fr); gap:20px; align-items:start; }
        .scene-sidebar { min-width:0; padding:16px; }
        .scene-sidebar h2 { margin-bottom:12px; }
        .scene-sidebar label { font-size:14px; margin:10px 0 4px; }
        .scene-sidebar input[type=search],.scene-sidebar select { padding:8px; font-size:14px; }
        .scene-sidebar select { margin-top:8px; }
        .scene-sidebar .check { margin:12px 0 8px; }
        .filter-label { position:absolute; width:1px; height:1px; padding:0; overflow:hidden; clip-path:inset(50%); white-space:nowrap; }
        #count { font-size:12px; margin:12px 0 8px; }
        #scene-list { display:flex; flex-direction:column; gap:2px; padding:4px; margin:0 -4px; }
        .scene-item { width:100%; text-align:left; margin:0; padding:6px 10px; line-height:1.35; background:transparent; color:inherit; border:1px solid transparent; overflow-wrap:anywhere; }
        .scene-item:hover { background:var(--secondary-background-color,#edf3f6); }
        .scene-item[aria-current=true] { background:var(--secondary-background-color,#edf3f6); border-color:var(--primary-color,#176b91); color:var(--primary-color,#176b91); font-weight:600; }
        .scene-item small { margin:0; font-size:12px; font-weight:400; }
        #scene-list-empty { font-size:14px; margin:12px 0 4px; }
        .scene-detail { min-width:0; }
        #notice { min-height:24px; } #notice.error { color:var(--error-color,#b3261e); } [hidden] { display:none !important; }
        @media(max-width:780px) { .scene-layout { grid-template-columns:1fr; gap:0; } main { padding:16px; } section { padding:16px; } [role=tablist] { gap:0; } [role=tab] { flex:1; padding:12px 6px; font-size:14px; } }
      </style>
      <main>
        <header><button class="menu" aria-label="Open sidebar">☰</button><h1>Stateful Scenes Revisited</h1></header>
        <p>See which scenes match your home, and exactly what needs to change.</p>
        <div id="notice" role="status" aria-live="polite">Connecting…</div>
        <div class="workspace">
          <div role="tablist" aria-label="Page configuration">
            <button id="tab-scenes" role="tab" aria-selected="true" aria-controls="scene-config" tabindex="0">Scene Config</button>
            <button id="tab-global" role="tab" aria-selected="false" aria-controls="global-config" tabindex="-1">Global Config</button>
          </div>
          <div id="scene-config" role="tabpanel" aria-labelledby="tab-scenes" tabindex="0">
          <div class="scene-layout">
          <section class="scene-sidebar" aria-labelledby="scenes-heading">
            <h2 id="scenes-heading">Scenes</h2>
            <label class="filter-label" for="scene-search">Search scenes by name</label><input id="scene-search" type="search" placeholder="Search scenes">
            <label class="filter-label" for="area">Filter by area</label><select id="area"><option value="">All areas</option><option value="__unassigned__">No area</option></select>
            <label class="check" title="Uses your configured scope: all scenes or scenes with the selected label."><input id="enabled-only" type="checkbox" checked>Only monitored scenes</label>
            <small id="count" role="status" aria-live="polite"></small>
            <nav id="scene-list" aria-label="Scenes" aria-describedby="count"></nav>
            <p id="scene-list-empty" hidden></p>
          </section>
          <section class="scene-detail" aria-labelledby="scene-name">
            <h2 id="scene-name">Selected scene</h2>
            <div id="switch-details" class="switch-details" hidden>
              <span>Switch:</span><code id="switch-entity"></code>
              <button id="copy-switch" type="button" aria-label="Copy switch entity ID" title="Copy switch entity ID" disabled>Copy</button>
              <span id="switch-state" role="status" aria-live="polite"></span>
            </div>
            <div role="tablist" aria-label="Scene features">
              <button id="tab-compare" role="tab" aria-selected="true" aria-controls="compare" tabindex="0">Compare/Debug</button>
              <button id="tab-configuration" role="tab" aria-selected="false" aria-controls="configuration" tabindex="-1">Configuration</button>
            </div>
            <div id="compare" role="tabpanel" aria-labelledby="tab-compare" tabindex="0">
              <h2>Scene comparison</h2><code id="scene-entity"></code>
              <div id="status" role="status" aria-live="polite">Waiting for scenes…</div>
              <small>All defined entity states and attributes are shown below. Ignored and non-restorable attributes do not affect the match. The switch turns on when every comparison matches.</small>
            <button id="activate" disabled>Activate scene</button>
            <div class="table"><table><thead><tr><th>Entity / attribute</th><th>Scene target</th><th>Current value</th><th>Result</th></tr></thead><tbody id="diff"></tbody></table></div>
            </div>
            <div id="configuration" role="tabpanel" aria-labelledby="tab-configuration" tabindex="0" hidden>
              <p id="configuration-empty">Choose a scene to configure its settings.</p>
              <div id="scene-options" hidden><h2>Scene settings</h2><form id="scene-form">
            <label for="tolerance">Brightness tolerance override</label><input id="tolerance" type="number" min="0" max="100" step="any" placeholder="Use global default">
            <small>Leave empty to follow the global default.</small>
            <label class="check"><input id="ignore" type="checkbox">Ignore all attributes (compare entity states only)</label>
            <fieldset id="attribute-options" aria-describedby="attribute-help"><legend>Attributes to compare</legend>
              <small id="attribute-help">Uncheck an attribute to ignore it for every entity in this scene. Global exclusions always apply, even to checked attributes.</small>
              <div id="attributes"></div>
            </fieldset>
            <button>Save scene settings</button>
              </form></div>
            </div>
          </section>
          </div>
          </div>
          <div id="global-config" role="tabpanel" aria-labelledby="tab-global" tabindex="0" hidden>
            <section><h2>Scene monitoring</h2><form id="scope-form">
              <label for="scope">Enable for</label><select id="scope">
                <option value="all">All scenes</option><option value="tag">Scenes with a label</option>
              </select>
              <div id="tag-options" hidden>
                <label for="tag">Scene label</label><select id="tag" aria-describedby="tag-help"></select>
                <div id="new-tag-options" hidden><label for="new-tag">New label name</label><input id="new-tag" type="text" maxlength="255"></div>
                <small id="tag-help">Select a Home Assistant label. Assign the chosen label to scene entities in their entity settings. Creating a label does not assign it to any scenes.</small>
              </div>
              <button>Save scene scope</button>
            </form></section>
            <section><h2>Global brightness tolerance</h2><form id="global-form">
              <label for="global">Percentage points</label><input id="global" type="number" min="0" max="100" step="any" required>
              <small>3 allows a brightness difference of up to 3% of the full 0–255 range. Zero requires an exact match.</small>
              <button>Save global default</button>
            </form></section>
            <section><h2>Global attribute ignore list</h2><form id="global-attributes-form">
              <label for="global-attributes">Ignored attributes</label>
              <textarea id="global-attributes" rows="5" aria-describedby="global-attributes-help" spellcheck="false"></textarea>
              <small id="global-attributes-help">Enter attribute names separated by lines or commas. These are ignored for every entity in every scene, in addition to each scene's exclusions. Leave empty to clear the list.</small>
              <button>Save global ignore list</button>
            </form></section>
          </div>
        </div>
      </main>`;
    this.$ = (id) => this.shadowRoot.getElementById(id);
    for (const tablist of this.shadowRoot.querySelectorAll('[role="tablist"]')) {
      const tabs = [...tablist.querySelectorAll('[role="tab"]')];
      const selectTab = (tab) => {
        for (const item of tabs) {
          const selected = item === tab;
          item.setAttribute("aria-selected", String(selected));
          item.tabIndex = selected ? 0 : -1;
          this.$(item.getAttribute("aria-controls")).hidden = !selected;
        }
        if (tab.id === "tab-compare") this.refreshComparison();
      };
      for (const [index, tab] of tabs.entries()) {
        tab.onclick = () => {
          selectTab(tab);
          if (tab.id === "tab-global") this.refreshLabels();
        };
        tab.onkeydown = (event) => {
          let next;
          if (event.key === "ArrowRight") next = tabs[(index + 1) % tabs.length];
          else if (event.key === "ArrowLeft") next = tabs[(index + tabs.length - 1) % tabs.length];
          else if (event.key === "Home") next = tabs[0];
          else if (event.key === "End") next = tabs[tabs.length - 1];
          if (!next) return;
          event.preventDefault();
          selectTab(next);
          next.focus();
        };
      }
    }
    this.shadowRoot.querySelector(".menu").onclick = () => this.dispatchEvent(new CustomEvent("hass-toggle-menu", { bubbles: true, composed: true }));
    this.$("copy-switch").onclick = () => this.copySwitchEntity();
    this.$("scene-search").oninput = () => this.render();
    this.$("enabled-only").onchange = () => this.render();
    this.$("area").onchange = () => this.render();
    this.$("ignore").onchange = () => { this.$("attribute-options").disabled = this.$("ignore").checked; };
    this.$("scope").onchange = () => this.renderScopeFields();
    this.$("tag").onchange = () => this.renderScopeFields();
    this.$("tag").onfocus = () => this.refreshLabels();
    this.$("scope-form").onsubmit = (event) => {
      event.preventDefault();
      const message = { type: "stateful_scenes_revisited/scope", scene_scope: this.$("scope").value };
      if (message.scene_scope === "tag") {
        if (this.$("tag").value === "__new__") message.new_tag = this.$("new-tag").value.trim();
        else message.scene_tag = this.$("tag").value;
      }
      this.save(message);
    };
    this.$("global-form").onsubmit = (event) => {
      event.preventDefault();
      this.save({ type: "stateful_scenes_revisited/settings", brightness_tolerance: Number(this.$("global").value) });
    };
    this.$("global-attributes-form").onsubmit = (event) => {
      event.preventDefault();
      this.save({ type: "stateful_scenes_revisited/settings", ignored_attributes: this.globalIgnoredAttributes() });
    };
    this.$("scene-form").onsubmit = (event) => {
      event.preventDefault();
      this.save({
        type: "stateful_scenes_revisited/scene_settings", scene_key: this.selected,
        brightness_tolerance: this.$("tolerance").value === "" ? null : Number(this.$("tolerance").value),
        ignore_attributes: this.$("ignore").checked,
        ignored_attributes: [...this.$("attributes").querySelectorAll("input")].filter(input => !input.checked).map(input => input.value),
      });
    };
    this.$("activate").onclick = async () => {
      const scene = this.data.scenes.find(s => s.key === this.selected);
      if (!scene) return;
      try {
        await this._hass.callService("scene", "turn_on", { entity_id: scene.entity_id });
        this.notice("Scene activated. Waiting for device states to match.");
      } catch (err) { this.notice(err.message || String(err), true); }
    };
  }

  get hass() { return this._hass; }
  set hass(value) {
    const changed = this._hass?.connection !== value.connection;
    this._hass = value;
    if (changed && this.isConnected) this.connect();
    this.renderSwitch();
  }
  connectedCallback() { if (this._hass) this.connect(); }
  disconnectedCallback() { this.generation++; this.unsubscribe?.(); this.unsubscribe = null; }

  async connect() {
    const generation = ++this.generation;
    this.unsubscribe?.();
    this.unsubscribe = null;
    try {
      const unsubscribe = await this._hass.connection.subscribeMessage(data => {
        if (generation !== this.generation) return;
        const first = !this.loaded;
        this.data = data;
        if (Array.isArray(data.tags)) this.labels = data.tags;
        this.loaded = true;
        this.render(first);
        if (first) this.notice("");
      }, { type: "stateful_scenes_revisited/subscribe" });
      if (generation !== this.generation) unsubscribe();
      else {
        this.unsubscribe = unsubscribe;
        await this.refreshLabels();
      }
    } catch (err) { this.notice(`Unable to load scenes: ${err.message || err}`, true); }
  }

  async refreshComparison() {
    const scene = this.data.scenes.find(item => item.key === this.selected);
    if (!scene) return;
    const generation = this.generation;
    const request = this.comparisonRequest = (this.comparisonRequest ?? 0) + 1;
    try {
      const result = await this._hass.callWS({ type: "stateful_scenes_revisited/comparison", scene_key: scene.key });
      if (generation !== this.generation || request !== this.comparisonRequest || this.selected !== scene.key) return;
      if (!Array.isArray(result?.comparison) || (result.supported && result.entity_count > 0 && !result.comparison.length)) {
        throw new Error("The server returned no entity comparisons. Reinstall the complete integration and restart Home Assistant.");
      }
      const current = this.data.scenes.find(item => item.key === scene.key);
      if (!current) return;
      Object.assign(current, result);
      this.render();
      this.notice("");
    } catch (err) {
      if (generation !== this.generation || request !== this.comparisonRequest || this.selected !== scene.key) return;
      this.notice(`Unable to load entity comparisons: ${err.message || err}`, true);
    }
  }

  renderSwitch() {
    const scene = this.data.scenes.find(scene => scene.key === this.selected);
    const entityId = scene?.switch_entity_id;
    this.$("switch-details").hidden = !scene;
    this.$("switch-entity").textContent = entityId ?? (scene?.monitored ? "Switch not available" : "No switch (scene is not monitored)");
    this.$("copy-switch").disabled = !entityId;
    const state = this._hass?.states?.[entityId]?.state ?? "unavailable";
    const indicator = this.$("switch-state");
    indicator.textContent = entityId ? `State: ${state}` : "";
    indicator.className = state === "on" ? "is-on" : state === "off" ? "" : "is-indeterminate";
    indicator.hidden = !entityId;
  }

  async copySwitchEntity() {
    const entityId = this.data.scenes.find(scene => scene.key === this.selected)?.switch_entity_id;
    if (!entityId) return;
    try {
      await navigator.clipboard.writeText(entityId);
      this.notice(`Copied ${entityId} to clipboard.`);
    } catch (err) {
      this.notice(`Could not copy entity ID. Select and copy it manually: ${entityId}`, true);
    }
  }

  async refreshLabels() {
    const generation = this.generation;
    const request = this.labelRequest = (this.labelRequest ?? 0) + 1;
    try {
      const labels = await this._hass.callWS({ type: "config/label_registry/list" });
      if (generation !== this.generation || request !== this.labelRequest) return;
      this.labels = labels.map(label => ({ id: label.label_id, name: label.name }))
        .sort((a, b) => a.name.localeCompare(b.name));
      this.renderScope();
    } catch (err) {
      if (generation !== this.generation || request !== this.labelRequest) return;
      this.notice(`Unable to load labels: ${err.message || err}`, true);
    }
  }

  notice(message, error = false) {
    this.$("notice").textContent = message;
    this.$("notice").classList.toggle("error", error);
  }

  async save(message) {
    try {
      await this._hass.callWS(message);
      this.notice("Settings saved.");
    } catch (err) { this.notice(`Could not save: ${err.message || err}`, true); }
  }

  renderScopeFields() {
    const tagged = this.$("scope").value === "tag";
    const adding = tagged && this.$("tag").value === "__new__";
    this.$("tag-options").hidden = !tagged;
    this.$("tag").disabled = !tagged;
    this.$("tag").required = tagged;
    this.$("new-tag-options").hidden = !adding;
    this.$("new-tag").disabled = !adding;
    this.$("new-tag").required = adding;
  }

  renderScope() {
    const tags = this.labels ?? this.data.tags ?? [];
    const scope = this.data.scene_scope ?? "all";
    const tag = this.data.scene_tag ?? "";
    const configSignature = JSON.stringify([scope, tag]);
    const changed = configSignature !== this.scopeSignature;
    const tagsSignature = JSON.stringify([tags, tag]);
    if (tagsSignature !== this.tagsSignature) {
      const draft = this.$("tag").value;
      const entries = [["", "Select a label"], ...tags.map(item => [item.id, item.name])];
      if (tag && !tags.some(item => item.id === tag)) entries.push([tag, "Selected label was deleted — choose another"]);
      entries.push(["__new__", "Add a new label…"]);
      this.$("tag").replaceChildren(...entries.map(([value, name]) => {
        const option = document.createElement("option");
        option.value = value; option.textContent = name; return option;
      }));
      this.$("tag").value = changed ? tag : entries.some(([value]) => value === draft) ? draft : "";
      this.tagsSignature = tagsSignature;
    }
    if (changed) {
      this.$("scope").value = scope;
      this.$("tag").value = tag;
      this.$("new-tag").value = "";
      this.scopeSignature = configSignature;
    }
    this.renderScopeFields();
  }

  render(loadSettings = false) {
    this.renderScope();
    const allScenes = this.data.scenes;
    const areas = [...new Map(allScenes.filter(s => s.area_id).map(s => [s.area_id, s.area_name])).entries()]
      .sort((a, b) => a[1].localeCompare(b[1]));
    const areaSelect = this.$("area");
    const areaSignature = JSON.stringify(areas);
    if (areaSignature !== this.areaSignature) {
      const selectedArea = areaSelect.value;
      areaSelect.replaceChildren(...[["", "All areas"], ["__unassigned__", "No area"], ...areas].map(([value, name]) => {
        const option = document.createElement("option");
        option.value = value; option.textContent = name; return option;
      }));
      areaSelect.value = selectedArea === "__unassigned__" || areas.some(([id]) => id === selectedArea) ? selectedArea : "";
      this.areaSignature = areaSignature;
    }
    const query = this.$("scene-search").value.trim().toLocaleLowerCase();
    const scenes = allScenes.filter(scene =>
      scene.name.toLocaleLowerCase().includes(query) &&
      (!this.$("enabled-only").checked || scene.monitored) &&
      (!areaSelect.value || (areaSelect.value === "__unassigned__" ? !scene.area_id : scene.area_id === areaSelect.value))
    );
    if (!scenes.some(s => s.key === this.selected)) {
      this.selected = scenes[0]?.key ?? null;
      loadSettings = true;
    }
    const list = this.$("scene-list");
    // Keep navigation and keyboard focus intact during live state updates.
    const signature = JSON.stringify(scenes.map(s => [s.key, s.name, s.area_name]));
    if (signature !== this.signature) {
      list.replaceChildren(...scenes.map(scene => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "scene-item";
        button.dataset.sceneKey = scene.key;
        button.textContent = scene.name;
        const area = document.createElement("small");
        area.textContent = scene.area_name || "No area";
        button.append(area);
        button.onclick = () => {
          if (this.selected === scene.key) return;
          this.selected = scene.key;
          this.render(true);
          if (!this.$("compare").hidden) this.refreshComparison();
        };
        return button;
      }));
      this.signature = signature;
    }
    for (const button of list.children) {
      if (button.dataset.sceneKey === this.selected) button.setAttribute("aria-current", "true");
      else button.removeAttribute("aria-current");
    }
    const emptyMessage = allScenes.length
      ? "No scenes match these filters. Try another name or change the filters."
      : "No scenes found. Create a scene in Home Assistant to get started.";
    this.$("scene-list-empty").hidden = scenes.length > 0;
    this.$("scene-list-empty").textContent = emptyMessage;
    this.$("count").textContent = `${scenes.length} of ${allScenes.length} scenes shown`;
    if (this.globalDefault !== this.data.brightness_tolerance) {
      this.$("global").value = this.data.brightness_tolerance;
      this.globalDefault = this.data.brightness_tolerance;
    }
    const globalIgnored = this.data.ignored_attributes ?? [];
    const globalIgnoreSignature = JSON.stringify(globalIgnored);
    if (this.globalIgnoreSignature !== globalIgnoreSignature) {
      this.$("global-attributes").value = globalIgnored.join("\n");
      this.globalIgnoreSignature = globalIgnoreSignature;
    }
    const scene = scenes.find(s => s.key === this.selected);
    this.renderSwitch();
    this.$("scene-options").hidden = !scene;
    this.$("configuration-empty").hidden = !!scene;
    this.$("activate").disabled = !scene;
    this.$("scene-entity").textContent = scene?.entity_id ?? "";
    if (!scene) {
      this.$("diff").replaceChildren();
      this.$("scene-name").textContent = "No scene selected";
      this.$("status").textContent = emptyMessage;
      this.$("configuration-empty").textContent = emptyMessage;
      return;
    }
    this.$("scene-name").textContent = scene.name;
    this.$("status").textContent = !scene.supported ? scene.issue : scene.matches
      ? `Matches · ${scene.entity_count} entities · brightness tolerance ${scene.options.brightness_tolerance}%`
      : `${scene.differences.length} differences · ${scene.entity_count} entities · brightness tolerance ${scene.options.brightness_tolerance}%`;
    const rows = [];
    for (const difference of scene.comparison ?? scene.differences ?? []) {
      const row = document.createElement("tr");
      row.className = difference.reason === "match" ? "is-match"
        : difference.reason === "ignored" ? "" : "is-mismatch";
      const values = [
        `${difference.entity_id} / ${difference.field}`,
        difference.reason === "target_unavailable" ? "Target unavailable" : this.format(difference.expected),
        difference.reason === "missing" ? "Entity missing" : difference.reason === "missing_attribute" ? "Attribute missing" : this.format(difference.actual),
        ({ match: "Matches", ignored: "Ignored",
          target_unavailable: "Cannot compare", missing: "Entity missing", unknown: "Entity unknown",
          unavailable: "Entity unavailable" })[difference.reason] ?? "Does not match",
      ];
      for (const value of values) {
        const cell = document.createElement("td"); cell.textContent = value; row.append(cell);
      }
      rows.push(row);
    }
    if (!rows.length) {
      const row = document.createElement("tr");
      const cell = document.createElement("td");
      cell.colSpan = 4;
      cell.textContent = scene.issue ?? (scene.entity_count > 0
        ? `Comparison details missing for ${scene.entity_count} entities. Reopen Compare/Debug to reload them.`
        : "No entity targets are available for this scene.");
      row.append(cell);
      rows.push(row);
    }
    this.$("diff").replaceChildren(...rows);
    if (loadSettings) {
      this.$("tolerance").value = scene.options.brightness_tolerance_override ?? "";
      this.$("ignore").checked = scene.options.ignore_attributes;
    }
    // Include saved exclusions so they can still be cleared after a scene is edited.
    const attributes = [...new Set([...scene.attributes, ...scene.options.ignored_attributes])].sort();
    const attributeSignature = JSON.stringify([scene.key, attributes, globalIgnored]);
    if (loadSettings || attributeSignature !== this.attributeSignature) {
      const draft = new Map([...this.$("attributes").querySelectorAll("input")].map(input => [input.value, input.checked]));
      this.$("attributes").replaceChildren(...attributes.map(attribute => {
        const label = document.createElement("label");
        label.className = "check";
        const input = document.createElement("input");
        input.type = "checkbox";
        input.value = attribute;
        input.checked = !loadSettings && draft.has(attribute) ? draft.get(attribute) : !scene.options.ignored_attributes.includes(attribute);
        label.append(input, document.createTextNode(attribute + (globalIgnored.includes(attribute) ? " (ignored globally)" : "")));
        return label;
      }));
      if (!attributes.length) this.$("attributes").textContent = "No attributes in this scene.";
      this.attributeSignature = attributeSignature;
    }
    this.$("attribute-options").disabled = this.$("ignore").checked;
  }
  globalIgnoredAttributes() {
    return [...new Set(this.$("global-attributes").value.split(/[\n,]+/).map(value => value.trim()).filter(Boolean))];
  }
  format(value) { return typeof value === "string" ? value : JSON.stringify(value); }
}
if (!customElements.get("stateful-scenes-revisited-panel")) customElements.define("stateful-scenes-revisited-panel", StatefulScenesRevisitedPanel);
