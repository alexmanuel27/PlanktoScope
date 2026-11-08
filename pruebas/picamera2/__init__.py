import sys, time, numpy as np, cv2
_rng = np.random.default_rng(0)
def escena(n, val, x0=0, x1=640, y0=0, y1=480, r=(3, 8)):
    e = np.zeros((480, 640))
    for _ in range(n):
        cv2.circle(e, (int(_rng.integers(x0, x1)), int(_rng.integers(y0, y1))), int(_rng.integers(*r)), val, -1)
    return e
RUIDO = 1.5
CAPAS = [(escena(150, 70.0), -237)]
class Picamera2:
    camera_controls = {}
    def create_preview_configuration(self, **k): return {}
    def configure(self, c): pass
    def start(self): pass
    def stop(self): pass
    def capture_buffer(self, name):
        s = sys.modules["app"].focus_step
        y = np.full((480, 640), 190.0) + _rng.normal(0, RUIDO, (480, 640))
        for e, p in CAPAS:
            y -= cv2.GaussianBlur(e, (0, 0), 0.3 + abs(s - p) / 8.0)
        buf = np.full(640 * 480 * 3 // 2, 128, np.uint8); buf[:640*480] = np.clip(y, 0, 255).ravel()
        time.sleep(0.01); return buf.tobytes()

class _Req:
    def __init__(self, cam): self.buf = cam.capture_buffer("lores")
    def make_buffer(self, name): return self.buf
    def make_array(self, name):
        y = np.frombuffer(self.buf, np.uint8)[:640 * 480].reshape(480, 640)
        g = cv2.resize(y, (2028, 1520), interpolation=cv2.INTER_CUBIC)
        return np.dstack([g, g, g])
    def release(self): pass
Picamera2.capture_request = lambda self: _Req(self)
