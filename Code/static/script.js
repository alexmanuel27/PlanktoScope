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
    event.target.classList.add('active');
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
            <td>${s.id}</td>
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

  capturePhoto() {
    this.logLive("Capturing photo...");
    fetch("/api/capture/photo")
      .then(res => res.json())
      .then(data => {
        if (data.status === "ok") {
          this.logLive(`Photo saved: ${data.file}`);
          // ✅ Mostrar resumen en consola web
          if (data.summary) {
            this.logLive(`Classification summary: ${data.summary}`);
          } else {
            this.logLive("No classification summary received");
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
      })
      .catch(err => console.error("Load config error:", err));
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
      method: "POST"
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

  init() {
    fetch("/api/focus/current")
      .then(r => r.json())
      .then(data => {
        this.focus_step = data.step;
        document.getElementById("focus-value").textContent = data.step;
      })
      .catch(() => {
        this.focus_step = 100;
        document.getElementById("focus-value").textContent = "100";
      });

    this.ledState = false;
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