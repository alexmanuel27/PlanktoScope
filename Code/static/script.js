const app = {
  currentView: 'samples',
  videoActive: false,
  ledState: false,
  focus_step: 100,
  ignore_focus_limits: false,

  showView(viewName) {
    document.querySelectorAll('.view').forEach(el => el.style.display = 'none');
    const target = document.getElementById('view-' + viewName);
    if (target) target.style.display = 'block';
    this.currentView = viewName;
    document.querySelectorAll('#sidebar a').forEach(a => a.classList.remove('active'));
    if (window.event && event.target && event.target.classList) event.target.classList.add('active');
    if (viewName === 'samples') this.loadSamples();
    if (viewName === 'live') {
      this.connectLiveConsole();
      this.updateLedButton();
    }
    if (viewName === 'settings') this.loadConfig();
  },

  loadSamples() {
    const body = document.getElementById("samplesBody");
    if (!body) return;
    fetch("/api/samples")
      .then(res => res.json())
      .then(samples => {
        body.innerHTML = samples.length ? samples.map(s => `
          <tr>
            <td>${s.type === 'photo' || s.type === 'video'
              ? `<a href="#" onclick="app.viewSample('${s.id}', '${s.type}'); return false;">${s.id}</a>`
              : s.id}</td>
            <td>${s.time}</td>
            <td>${s.type}</td>
            <td>
              <a href="/download/${encodeURIComponent(s.id)}" class="btn">Download</a>
              <button class="btn btn-danger" onclick="app.deleteSample('${s.id}')">Delete</button>
            </td>
          </tr>
        `).join('') : '<tr><td colspan="4">No samples</td></tr>';
      })
      .catch(err => {
        body.innerHTML = `<tr><td colspan="4" style="color:#ef4444;">Load error: ${err.message}</td></tr>`;
      });
  },

  viewSample(id, type) {
    const v = document.getElementById("viewer");
    const url = `/samples/${encodeURIComponent(id)}`;
    v.innerHTML = type === "video" ? `<video src="${url}" controls autoplay></video>`
      : `<div class="viewer-box"><img id="viewer-img" src="${url}" alt="${id}">
         <div class="viewer-bar"><button class="btn" onclick="app.startCalibration()">Calibrate (µm/px)</button>
         <span id="calib-info"></span></div></div>`;
    v.style.display = "flex";
  },

  // Calibración: foto del portaobjetos micrométrico, clic en dos marcas y la distancia real en µm.
  startCalibration() {
    const img = document.getElementById("viewer-img"), info = document.getElementById("calib-info");
    const box = img.parentElement, puntos = [];
    box.querySelectorAll(".calib-dot").forEach(d => d.remove());
    info.textContent = "Click two marks of the scale";
    img.style.cursor = "crosshair";
    img.onclick = (e) => {
      const r = img.getBoundingClientRect();
      puntos.push([(e.clientX - r.left) * img.naturalWidth / r.width, (e.clientY - r.top) * img.naturalHeight / r.height]);
      const dot = document.createElement("span");
      dot.className = "calib-dot";
      dot.style.left = `${e.clientX - box.getBoundingClientRect().left}px`;
      dot.style.top = `${e.clientY - box.getBoundingClientRect().top}px`;
      box.appendChild(dot);
      if (puntos.length < 2) return;
      img.onclick = null;
      img.style.cursor = "default";
      const px = Math.hypot(puntos[1][0] - puntos[0][0], puntos[1][1] - puntos[0][1]);
      const um = parseFloat((prompt(`${px.toFixed(1)} px between the marks. Real distance in µm?`) || "").replace(",", "."));
      if (!(um > 0) || px < 1) { info.textContent = "Calibration cancelled"; return; }
      fetch("/api/calibration", { method: "POST", headers: { "Content-Type": "application/json" },
                                  body: JSON.stringify({ um_por_px: um / px }) })
        .then(res => res.json())
        .then(d => { info.textContent = d.error ? d.error : `${d.um_por_px.toFixed(4)} µm/px saved (${px.toFixed(1)} px = ${um} µm)`; });
    };
  },

  captureBackground() {
    this.logLive("Background: fill the capillary with clean water, LED on...");
    fetch("/api/background", { method: "POST" })
      .then(res => res.json())
      .then(d => this.logLive(d.error ? d.error : "Background saved"))
      .catch(err => this.logLive(`Background error: ${err.message}`));
  },

  connectLiveConsole() {
    const consoleEl = document.getElementById("live-console");
    if (!consoleEl) return;
    consoleEl.innerHTML = "Connecting...";
    if (this.eventSource) this.eventSource.close();
    this.eventSource = new EventSource("/api/console/stream");
    this.eventSource.onopen = () => { consoleEl.innerHTML = ""; };
    this.eventSource.onmessage = (e) => {
      const line = document.createElement("div");
      line.textContent = e.data;
      consoleEl.appendChild(line);
      consoleEl.scrollTop = consoleEl.scrollHeight;
    };
  },

  autoFocus() {
    this.logLive("Autofocus en marcha (unos segundos)...");
    fetch("/api/focus/auto")
      .then(res => res.json())
      .then(data => {
        if (data.error) { this.logLive(data.error); return; }
        this.focus_step = data.step;
        document.getElementById("focus-value").textContent = data.step;
        this.logLive(`Autofocus: ${data.step}`);
      })
      .catch(err => this.logLive(`Autofocus error: ${err.message}`));
  },

  focusMotor(dir) {
    fetch(`/api/focus/${dir}`)
      .then(res => res.json())
      .then(data => {
        if (data.error) {
          this.logLive(data.error);
        } else {
          this.focus_step = data.step;
          document.getElementById("focus-value").textContent = data.step;
          this.logLive(`Focus step: ${data.step}`);
        }
      })
      .catch(err => {
        this.logLive(`Focus error: ${err.message}`);
      });
  },

  captureLayers() {
    this.logLive("Capturing focus layers (~30 s)...");
    fetch("/api/capture/layers")
      .then(res => res.json())
      .then(data => {
        if (data.error) { this.logLive(data.error); return; }
        this.focus_step = data.step;
        document.getElementById("focus-value").textContent = data.step;
        this.logLive(`Layers ${data.capas.join(", ")} -> ${data.files.join(", ")}`);
        this.logLive(`Objects: ${data.unicos} unique (${data.objetos - data.unicos} repeated across layers)`);
        if (this.currentView === "samples") this.loadSamples();
      })
      .catch(err => this.logLive(`Layers error: ${err.message}`));
  },

  capturePhoto() {
    this.logLive("Capturing photo...");
    fetch("/api/capture/photo")
      .then(res => res.json())
      .then(data => {
        if (data.status === "ok") {
          this.logLive(`Photo saved: ${data.file}`);
          
          // Mostrar resumen de clasificación
          if (data.summary) {
            this.logLive(`Classification summary: ${data.summary}`);
          }
          
          if (this.currentView === "samples") this.loadSamples();
        } else {
          this.logLive("Capture failed");
        }
      })
      .catch(err => {
        this.logLive(`Capture error: ${err.message}`);
      });
  },

  toggleVideo() {
    const btn = document.getElementById("videoBtn");
    const action = this.videoActive ? "stop" : "start";
    fetch(`/api/capture/video/${action}`)
      .then(() => {
        this.videoActive = !this.videoActive;
        btn.textContent = this.videoActive ? "Stop Video" : "Start Video";
        btn.style.background = this.videoActive ? "#ef4444" : "#38bdf8";
        this.logLive(this.videoActive ? "Video recording started" : "Video recording stopped");
      });
  },

  takeSample() {
    this.logLive("Taking sample...");
    fetch("/api/sample/take")
      .then(res => res.json())
      .then(data => {
        this.logLive(`Sample saved: ${data.sample.id}`);
        if (this.currentView === "samples") this.loadSamples();
      });
  },

  toggleLed() {
    fetch("/api/led/toggle")
      .then(res => res.json())
      .then(data => {
        this.ledState = data.state;
        this.updateLedButton();
        this.logLive(`LED ${data.status}`);
        this.pollSeries();   // quitar el aviso de "LED blinking" del panel
      });
  },

  updateLedButton() {
    const btn = document.getElementById("ledBtn");
    if (btn) {
      const status = this.ledState ? "ON" : "OFF";
      btn.textContent = `LED ${status}`;
      btn.style.background = this.ledState ? "#8b5cf6" : "#38bdf8";
    }
  },

  deleteSample(filename) {
    if (!confirm(`Delete ${filename}?`)) return;
    
    fetch(`/api/samples/delete/${encodeURIComponent(filename)}`, {
      method: "DELETE"
    })
    .then(res => {
      if (res.ok) {
        this.logLive(`Deleted: ${filename}`);
        if (this.currentView === "samples") this.loadSamples();
      } else {
        throw new Error("Delete failed");
      }
    })
    .catch(err => {
      this.logLive(`Delete error: ${err.message}`);
    });
  },

  deleteAllSamples() {
    if (!confirm("Delete ALL samples? This cannot be undone!")) return;
    
    fetch("/api/samples/delete/all", {
      method: "DELETE"
    })
    .then(res => {
      if (res.ok) {
        this.logLive("All samples deleted");
        if (this.currentView === "samples") this.loadSamples();
      } else {
        throw new Error("Delete all failed");
      }
    })
    .catch(err => {
      this.logLive(`Delete all error: ${err.message}`);
    });
  },

  logLive(msg) {
    const live = document.getElementById("live-console");
    if (live) {
      const line = document.createElement("div");
      line.textContent = `[${new Date().toLocaleTimeString()}] ${msg}`;
      live.appendChild(line);
      live.scrollTop = live.scrollHeight;
    }
  },

  loadConfig() {
    fetch("/api/config")
      .then(res => res.json())
      .then(config => {
        document.getElementById("stepper1-dir").value = config.stepper1.dir_pin;
        document.getElementById("stepper1-step").value = config.stepper1.step_pin;
        document.getElementById("stepper1-enable").value = config.stepper1.enable_pin;
        document.getElementById("stepper1-steps").value = config.stepper1.steps_take_sample;
        document.getElementById("stepper2-dir").value = config.stepper2.dir_pin;
        document.getElementById("stepper2-step").value = config.stepper2.step_pin;
        document.getElementById("stepper2-enable").value = config.stepper2.enable_pin;
        document.getElementById("stepper2-steps").value = config.stepper2.steps_focus;
        document.getElementById("stepper2-focus-min").value = config.stepper2.focus_min || 40;
        document.getElementById("stepper2-focus-max").value = config.stepper2.focus_max || 60;
        const cam = config.camara || {}, ppm = config.stepper1.pasos_por_ml || 0;
        document.getElementById("calib-umpx").value = cam.um_por_px ? cam.um_por_px.toFixed(4) : "not calibrated";
        document.getElementById("calib-prof").value = cam.profundidad_um || "";
        document.getElementById("calib-pasos").value = 10 * config.stepper1.steps_take_sample;
        const vf = cam.um_por_px && cam.profundidad_um ? 640 * cam.um_por_px * 480 * cam.um_por_px * cam.profundidad_um / 1e12 : 0;
        document.getElementById("calib-resumen").textContent =
          `Volume per photo: ${vf ? vf.toExponential(2) + " mL" : "—"} · pump: ${ppm ? ppm.toFixed(0) + " steps/mL (" +
          (config.stepper1.steps_take_sample / ppm).toFixed(4) + " mL per Take Sample)" : "not calibrated"}` +
          (vf ? "" : " · concentration needs µm/px and depth");
      })
      .catch(err => console.error("Load config error:", err));
  },

  postCalibration(url, body) {
    fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })
      .then(r => r.json())
      .then(d => { document.getElementById("config-status").textContent = d.error ? d.error : "Calibration saved"; this.loadConfig(); });
  },

  saveDepth() {
    this.postCalibration("/api/calibration/depth", { profundidad_um: document.getElementById("calib-prof").value });
  },

  savePump() {
    this.postCalibration("/api/calibration/pump", { pasos: document.getElementById("calib-pasos").value,
                                                    ml: document.getElementById("calib-ml").value });
  },

  saveConfig() {
    const config = {
      stepper1: {
        dir_pin: document.getElementById("stepper1-dir").value,
        step_pin: document.getElementById("stepper1-step").value,
        enable_pin: document.getElementById("stepper1-enable").value,
        steps_take_sample: document.getElementById("stepper1-steps").value
      },
      stepper2: {
        dir_pin: document.getElementById("stepper2-dir").value,
        step_pin: document.getElementById("stepper2-step").value,
        enable_pin: document.getElementById("stepper2-enable").value,
        steps_focus: document.getElementById("stepper2-steps").value,
        focus_min: document.getElementById("stepper2-focus-min").value,
        focus_max: document.getElementById("stepper2-focus-max").value
      }
    };
    fetch("/api/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(config)
    })
    .then(res => {
      if (res.ok) {
        document.getElementById("config-status").textContent = "Configuration saved!";
        document.getElementById("config-status").style.color = "green";
        setTimeout(() => document.getElementById("config-status").textContent = "", 3000);
      } else {
        throw new Error("Save failed");
      }
    })
    .catch(err => {
      document.getElementById("config-status").textContent = "Error: " + err.message;
      document.getElementById("config-status").style.color = "red";
    });
  },

  toggleIgnoreLimits() {
    const ignore = document.getElementById("ignore-focus-limits").checked;
    fetch("/api/focus/ignore", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({ignore: ignore})
    })
    .then(res => res.json())
    .then(data => {
      this.ignore_focus_limits = data.ignore;
      this.logLive(`Focus limits ignored: ${this.ignore_focus_limits}`);
    })
    .catch(err => {
      this.logLive(`Toggle ignore limits error: ${err.message}`);
    });
  },

  // ---------- Serie temporal ----------
  SERIES_MUESTRA_S: 40,   // lo que tarda una muestra (bomba + espera + capas), aproximado

  seriesInputs() {
    const modo = document.querySelector('input[name="series-mode"]:checked').value;
    const valor = parseFloat(document.getElementById("series-value").value);
    const intervalo = parseFloat(document.getElementById("series-interval").value);
    const espera = parseFloat(document.getElementById("series-wait").value);
    const n = modo === "muestras" ? Math.floor(valor) : Math.ceil(valor / intervalo);
    return { modo, valor, intervalo, espera, n };
  },

  seriesSummary() {
    const { intervalo, n } = this.seriesInputs();
    const el = document.getElementById("series-summary");
    if (!(n >= 1) || !(intervalo > 0)) { el.textContent = "Check the values"; return; }
    const dur = (n - 1) * intervalo + this.SERIES_MUESTRA_S;
    el.textContent = `${n} samples, every ${intervalo} s — about ${(dur / 60).toFixed(1)} min` +
      (intervalo < this.SERIES_MUESTRA_S ? ` ⚠ interval shorter than one sample (~${this.SERIES_MUESTRA_S} s)` : "");
  },

  startSeries() {
    const p = this.seriesInputs();
    if (p.intervalo < this.SERIES_MUESTRA_S &&
        !confirm(`Each sample takes about ${this.SERIES_MUESTRA_S} s; with ${p.intervalo} s the samples will run back to back. Start anyway?`)) return;
    fetch("/api/series/start", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(p) })
      .then(res => res.json())
      .then(d => {
        if (d.error) { this.logLive(d.error); return; }
        this.logLive(`Series started: ${d.n} samples -> ${d.fichero}`);
        this.pollSeries();
      })
      .catch(err => this.logLive(`Series error: ${err.message}`));
  },

  stopSeries() {
    fetch("/api/series/stop", { method: "POST" }).then(() => this.logLive("Series: stopping after the current sample"));
  },

  pollSeries() {
    clearTimeout(this.seriesTimer);
    fetch("/api/series/state")
      .then(res => res.json())
      .then(s => {
        const st = document.getElementById("series-status");
        document.getElementById("series-start").disabled = s.activa;
        if (s.activa) {
          this.loadSession();
          st.textContent = `${s.estado} · ${s.filas.length}/${s.n} done` + (s.siguiente_s ? ` · next in ${Math.round(s.siguiente_s)} s` : "");
          this.seriesTimer = setTimeout(() => this.pollSeries(), 3000);
        } else if (s.fichero) {
          st.textContent = `Series ${s.estado}: ${s.filas.length}/${s.n} samples in ${s.fichero}` + (s.error ? ` (${s.error})` : "") +
            (s.parpadeo ? " — LED blinking (press LED to turn it off)" : "");
          if (this.seriesWasActive && this.currentView === "samples") this.loadSamples();
        }
        this.seriesWasActive = s.activa;
        if (s.led !== undefined && s.led !== this.ledState) { this.ledState = s.led; this.updateLedButton(); }  // la serie lo enciende y apaga
        this.drawSeries(s.filas);
      })
      .catch(() => { this.seriesTimer = setTimeout(() => this.pollSeries(), 5000); });   // Wi-Fi cortado: reintentar
  },

  drawSeries(filas) {
    const cv = document.getElementById("series-chart"), ctx = cv.getContext("2d");
    const W = cv.width, H = cv.height, m = { l: 30, r: 8, t: 8, b: 22 };
    ctx.clearRect(0, 0, W, H);
    const legend = document.getElementById("series-legend");
    legend.innerHTML = "";
    if (!filas || !filas.length) return;
    const clases = [...new Set(filas.flatMap(f => Object.keys(f.conteo)))].sort();
    const series = [["total", filas.map(f => f.objetos)], ...clases.map(c => [c, filas.map(f => f.conteo[c] || 0)])];
    const colores = ["#111827", "#2563eb", "#16a34a", "#dc2626", "#d97706", "#7c3aed", "#0891b2", "#db2777", "#65a30d"];
    const tMax = Math.max(1, ...filas.map(f => f.t_s)), yMax = Math.max(1, ...filas.map(f => f.objetos));
    const X = t => m.l + (W - m.l - m.r) * t / tMax, Y = v => H - m.b - (H - m.t - m.b) * v / yMax;
    ctx.strokeStyle = "#9ca3af"; ctx.fillStyle = "#6b7280"; ctx.font = "10px sans-serif"; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(m.l, m.t); ctx.lineTo(m.l, H - m.b); ctx.lineTo(W - m.r, H - m.b); ctx.stroke();
    ctx.fillText(yMax, 2, m.t + 8); ctx.fillText("0", 18, H - m.b); ctx.fillText(`${Math.round(tMax)} s`, W - m.r - 34, H - 6);
    series.forEach(([nombre, valores], k) => {
      const color = colores[k % colores.length];
      ctx.strokeStyle = ctx.fillStyle = color; ctx.lineWidth = nombre === "total" ? 2 : 1.5;
      ctx.beginPath();
      valores.forEach((v, i) => { const x = X(filas[i].t_s), y = Y(v); i ? ctx.lineTo(x, y) : ctx.moveTo(x, y); });
      ctx.stroke();
      valores.forEach((v, i) => { ctx.beginPath(); ctx.arc(X(filas[i].t_s), Y(v), 2.5, 0, 2 * Math.PI); ctx.fill(); });
      const item = document.createElement("span");
      item.innerHTML = `<i style="background:${color}"></i>${nombre}: ${valores[valores.length - 1]}`;
      legend.appendChild(item);
    });
  },

  updateDisk() {
    fetch("/api/disk")
      .then(res => res.json())
      .then(d => {
        const usado = d.used / d.total, gb = b => (b / 1e9).toFixed(1);
        const fill = document.getElementById("disk-fill");
        fill.style.width = `${(usado * 100).toFixed(0)}%`;
        fill.className = usado > 0.9 ? "lleno" : usado > 0.8 ? "casi" : "";
        document.getElementById("disk-text").textContent = `SD ${gb(d.free)} GB free of ${gb(d.total)} GB`;
      })
      .catch(() => {});
  },

  // ---------- Sesión del dataset ----------
  showSession(d) {
    const s = d.sesion, campos = ["especie", "origen", "dilucion", "edad", "operador", "notas"];
    campos.forEach(c => document.getElementById(`session-${c}`).disabled = !!s);
    document.getElementById("session-start").disabled = !!s;
    document.getElementById("session-end").disabled = !s;
    document.getElementById("session-status").textContent = s
      ? `${s.sesion} active: ${s.especie_cultivo}, photos from ${s.fotos_desde} (next: ${d.siguiente_foto})`
      : "No session — photos are not linked to a culture";
    if (s) {
      document.getElementById("session-especie").value = s.especie_cultivo;
      document.getElementById("session-origen").value = s.origen || "cultivo";
      document.getElementById("session-dilucion").value = s.dilucion;
      document.getElementById("session-edad").value = s.edad_cultivo_dias;
      document.getElementById("session-operador").value = s.operador;
      document.getElementById("session-notas").value = s.notas;
    }
  },

  loadSession() {
    fetch("/api/session").then(r => r.json()).then(d => this.showSession(d)).catch(() => {});
  },

  startSession() {
    const v = id => document.getElementById(id).value;
    const body = { especie_cultivo: v("session-especie"), origen: v("session-origen"), dilucion: v("session-dilucion"),
                   edad_cultivo_dias: v("session-edad"), operador: v("session-operador"), notas: v("session-notas") };
    fetch("/api/session/start", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })
      .then(r => r.json())
      .then(d => {
        if (d.error) { this.logLive(d.error); return; }
        this.logLive(`Session ${d.sesion.sesion} started (${d.sesion.especie_cultivo})`);
        this.loadSession();
      });
  },

  endSession() {
    fetch("/api/session/end", { method: "POST" })
      .then(r => r.json())
      .then(d => {
        this.logLive(d.error ? d.error : `Session ${d.sesion.sesion} closed: photos ${d.sesion.fotos_desde}–${d.sesion.fotos_hasta} (samples/sesiones.csv)`);
        this.loadSession();
      });
  },

  init() {
    this.loadSession();
    this.updateDisk();
    setInterval(() => this.updateDisk(), 30000);
    ["series-value", "series-interval"].forEach(id => document.getElementById(id).addEventListener("input", () => this.seriesSummary()));
    document.querySelectorAll('input[name="series-mode"]').forEach(r => r.addEventListener("change", () => this.seriesSummary()));
    this.seriesSummary();
    this.pollSeries();   // si había una serie en marcha (otra pestaña, página recargada), recuperar su estado
    // La Raspberry no tiene internet ni reloj propio: le pasamos la hora de este ordenador
    fetch("/api/time", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({epoch: Date.now() / 1000})
    }).catch(() => {});

    // Estado real del equipo: el mismo en cualquier ordenador que abra la página
    fetch("/api/state")
      .then(r => r.json())
      .then(data => {
        this.focus_step = data.focus_step;
        document.getElementById("focus-value").textContent = data.focus_step;
        this.ledState = data.led;
        this.updateLedButton();
        this.ignore_focus_limits = data.ignore_focus_limits;
        document.getElementById("ignore-focus-limits").checked = data.ignore_focus_limits;
      })
      .catch(() => {
        document.getElementById("focus-value").textContent = "—";   // nunca inventar un valor
      });

    this.showView('samples');
    const menuToggle = document.getElementById("menu-toggle");
    const overlay = document.getElementById("overlay");
    const sidebar = document.getElementById("sidebar");
    if (menuToggle) {
      menuToggle.addEventListener("click", () => {
        sidebar.classList.add("active");
        overlay.classList.add("active");
      });
    }
    if (overlay) {
      overlay.addEventListener("click", () => {
        sidebar.classList.remove("active");
        overlay.classList.remove("active");
      });
    }
    document.addEventListener("click", (e) => {
      if (window.innerWidth <= 768) {
        const outside = !sidebar.contains(e.target) && menuToggle && !menuToggle.contains(e.target);
        if (outside && sidebar.classList.contains("active")) {
          sidebar.classList.remove("active");
          overlay.classList.remove("active");
        }
      }
    });

    document.getElementById("ignore-focus-limits").addEventListener("change", () => {
      this.toggleIgnoreLimits();
    });
  }
};

document.addEventListener("DOMContentLoaded", () => app.init());
