// script.js — PlanktoScope frontend
const app = {
  currentView: 'samples',
  videoActive: false,

  // Cambiar vista
  showView(viewName) {
    document.querySelectorAll('.view').forEach(el => el.style.display = 'none');
    const target = document.getElementById('view-' + viewName);
    if (target) target.style.display = 'block';
    this.currentView = viewName;

    // Actualizar menú activo
    document.querySelectorAll('#sidebar a').forEach(a => a.classList.remove('active'));
    event.target.classList.add('active');

    // Cargar muestras si es la vista correcta
    if (viewName === 'samples') {
      this.loadSamples();
    }

    // Conectar consola solo en Live View
    if (viewName === 'live') {
      this.connectLiveConsole();
    }
  },

  // Cargar lista de archivos desde /samples
  async loadSamples() {
    const body = document.getElementById("samplesBody");
    if (!body) return;
    try {
      const res = await fetch("/api/samples");
      const files = await res.json();
      body.innerHTML = files.length ? files.map(f => `
        <tr>
          <td>${f.id}</td>
          <td>${f.time}</td>
          <td>${f.type}</td>
          <td><a href="/download/${encodeURIComponent(f.id)}" class="btn">Download</a></td>
        </tr>
      `).join('') : '<tr><td colspan="4" style="text-align:center;">No files</td></tr>';
    } catch (err) {
      body.innerHTML = `<tr><td colspan="4" style="color:#ef4444;">Load error: ${err.message}</td></tr>`;
    }
  },

  // Conectar solo la consola de Live View
  connectLiveConsole() {
    const consoleEl = document.getElementById("live-console");
    if (!consoleEl) return;

    // Limpiar consola anterior
    consoleEl.innerHTML = "Connecting...";

    // Cerrar conexión previa si existe
    if (this.eventSource) {
      this.eventSource.close();
    }

    this.eventSource = new EventSource("/api/console/stream");
    this.eventSource.onmessage = (e) => {
      const line = document.createElement("div");
      line.textContent = e.data;
      consoleEl.appendChild(line);
      consoleEl.scrollTop = consoleEl.scrollHeight;
    };
    this.eventSource.onerror = () => {
      if (consoleEl.textContent.includes("Connecting")) {
        consoleEl.textContent = "[Error] Console disconnected.";
      }
    };
  },

  // Controles de cámara
  async focusMotor(dir) {
    const res = await fetch(`/api/focus/${dir}`);
    const data = await res.json();
    document.getElementById("focus-value").textContent = data.step;
    this.logLive(`Focus step: ${data.step}`);
  },

  async capturePhoto() {
    this.logLive("Capturing photo...");
    const res = await fetch("/api/capture/photo");
    const data = await res.json();
    this.logLive(data.status === "ok" ? `Photo saved: ${data.file}` : "Capture failed");
    if (this.currentView === "samples") this.loadSamples();
  },

  async toggleVideo() {
    const btn = document.getElementById("videoBtn");
    if (!this.videoActive) {
      await fetch("/api/capture/video/start");
      this.videoActive = true;
      btn.textContent = "Stop Video";
      btn.style.background = "#ef4444";
    } else {
      await fetch("/api/capture/video/stop");
      this.videoActive = false;
      btn.textContent = "Start Video";
      btn.style.background = "#38bdf8";
    }
    this.logLive(this.videoActive ? "Video recording started" : "Video recording stopped");
  },

  async takeSample() {
    this.logLive("Taking sample...");
    const res = await fetch("/api/sample/take");
    const data = await res.json();
    this.logLive(`Sample data saved: ${data.sample.id}`);
    if (this.currentView === "samples") this.loadSamples();
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

  // Inicialización
  init() {
    this.showView('samples'); // vista inicial

    // Menú táctil
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
  }
};

// Iniciar cuando el DOM esté listo
document.addEventListener("DOMContentLoaded", () => app.init());