const app = {
  currentView: 'samples',
  videoActive: false,

  showView(viewName) {
    document.querySelectorAll('.view').forEach(el => el.style.display = 'none');
    const target = document.getElementById('view-' + viewName);
    if (target) target.style.display = 'block';
    this.currentView = viewName;
    document.querySelectorAll('#sidebar a').forEach(a => a.classList.remove('active'));
    event.target.classList.add('active');
    if (viewName === 'samples') this.loadSamples();
    if (viewName === 'live') this.connectLiveConsole();
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
            <td>${s.id}</td>
            <td>${s.time}</td>
            <td>${s.type}</td>
            <td><a href="/download/${encodeURIComponent(s.id)}" class="btn">Download</a></td>
          </tr>
        `).join('') : '<tr><td colspan="4">No samples</td></tr>';
      })
      .catch(err => {
        body.innerHTML = `<tr><td colspan="4" style="color:#ef4444;">Load error: ${err.message}</td></tr>`;
      });
  },

  connectLiveConsole() {
    const consoleEl = document.getElementById("live-console");
    if (!consoleEl) return;
    consoleEl.innerHTML = "Connecting...";
    if (this.eventSource) this.eventSource.close();
    this.eventSource = new EventSource("/api/console/stream");
    this.eventSource.onmessage = (e) => {
      const line = document.createElement("div");
      line.textContent = e.data;
      consoleEl.appendChild(line);
      consoleEl.scrollTop = consoleEl.scrollHeight;
    };
  },

  focusMotor(dir) {
    fetch(`/api/focus/${dir}`)
      .then(res => res.json())
      .then(data => {
        document.getElementById("focus-value").textContent = data.step;
        this.logLive(`Focus step: ${data.step}`);
      });
  },

  capturePhoto() {
    this.logLive("Capturing photo...");
    fetch("/api/capture/photo")
      .then(res => res.json())
      .then(data => {
        this.logLive(data.status === "ok" ? `Photo saved: ${data.file}` : "Capture failed");
        if (this.currentView === "samples") this.loadSamples();
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
        document.getElementById("stepper1-steps").value = config.stepper1.steps_take_sample;
        document.getElementById("stepper2-dir").value = config.stepper2.dir_pin;
        document.getElementById("stepper2-step").value = config.stepper2.step_pin;
        document.getElementById("stepper2-steps").value = config.stepper2.steps_focus;
      })
      .catch(err => console.error("Load config error:", err));
  },

  saveConfig() {
    const config = {
      stepper1: {
        dir_pin: document.getElementById("stepper1-dir").value,
        step_pin: document.getElementById("stepper1-step").value,
        steps_take_sample: document.getElementById("stepper1-steps").value
      },
      stepper2: {
        dir_pin: document.getElementById("stepper2-dir").value,
        step_pin: document.getElementById("stepper2-step").value,
        steps_focus: document.getElementById("stepper2-steps").value
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

  init() {
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
  }
};

document.addEventListener("DOMContentLoaded", () => app.init());
