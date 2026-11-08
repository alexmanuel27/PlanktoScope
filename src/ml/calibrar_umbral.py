"""Umbral de rechazo y calibración del clasificador sobre el subconjunto limpio (mismo criterio que evaluar_modelo.py).

1. Compara el preprocesado del entrenamiento (keras load_img, interpolación 'nearest') con el de la app
   (PIL resize por defecto, bicúbica): si difieren en exactitud, la app debe usar el del entrenamiento.
2. Umbral de confianza máxima (MSP) que conserva el 95 % de las imágenes de clases conocidas
   (recomendación de arXiv:2605.15835 cuando hay pocos datos de validación).
3. Temperature scaling (p_T ∝ p^(1/T)): T por mínima log-verosimilitud y ECE antes/después.

  python calibrar_umbral.py --modelo m.tflite --labels labels.json --dataset dataset_pm --out salida/
"""
import argparse, json, os
import numpy as np
from PIL import Image
from evaluar_modelo import imagenes, md5, dhash, hamming_min, UMBRAL_DHASH

RECALL_OBJETIVO = 0.95


def subconjunto_limpio(raiz):
    train = list(imagenes(raiz, "training"))
    md5_train = {md5(p) for p, _ in train}
    dh_train = np.array([dhash(p) for p, _ in train], dtype=np.uint64)
    vistos, limpio = set(), []
    for split in ("test", "validation"):
        for p, c in imagenes(raiz, split):
            h = md5(p)
            if h in md5_train or h in vistos or hamming_min(dhash(p), dh_train) <= UMBRAL_DHASH:
                continue
            vistos.add(h); limpio.append((p, c))
    return limpio


def ece(P, y, bins=10):
    conf, ok = P.max(1), P.argmax(1) == y
    e = 0.0
    for lo in np.linspace(0, 1, bins, endpoint=False):
        m = (conf > lo) & (conf <= lo + 1 / bins)
        if m.any():
            e += m.mean() * abs(ok[m].mean() - conf[m].mean())
    return float(e)


def con_temperatura(P, T):
    z = np.log(np.clip(P, 1e-12, 1)) / T
    z -= z.max(1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(1, keepdims=True)


def main():
    ap = argparse.ArgumentParser()
    for k in ("--modelo", "--labels", "--dataset", "--out"):
        ap.add_argument(k, required=True)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    import tensorflow as tf
    from keras.utils import load_img

    idx = json.load(open(a.labels))
    clases = [c for c, _ in sorted(idx.items(), key=lambda kv: kv[1])]
    limpio = subconjunto_limpio(a.dataset)
    y = np.array([clases.index(c) for _, c in limpio])

    it = tf.lite.Interpreter(model_path=a.modelo); it.allocate_tensors()
    i_in, i_out = it.get_input_details()[0], it.get_output_details()[0]

    def predecir(cargar):
        out = []
        for p, _ in limpio:
            it.set_tensor(i_in["index"], (np.asarray(cargar(p), dtype=np.float32) / 255.0)[None]); it.invoke()
            out.append(it.get_tensor(i_out["index"])[0])
        return np.array(out)

    P = {"entrenamiento (nearest)": predecir(lambda p: load_img(p, target_size=(224, 224))),
         "app (PIL bicúbica)": predecir(lambda p: Image.open(p).convert("RGB").resize((224, 224)))}
    res = {"n": int(len(y)), "preprocesado": {k: {"exactitud": float(np.mean(v.argmax(1) == y))} for k, v in P.items()}}

    Pe = P["entrenamiento (nearest)"]
    msp, ok = Pe.max(1), Pe.argmax(1) == y
    t = float(np.quantile(msp, 1 - RECALL_OBJETIVO))
    acept = msp >= t
    res["umbral_msp"] = {"recall_objetivo": RECALL_OBJETIVO, "umbral": t,
                         "conservadas": int(acept.sum()), "rechazadas": int((~acept).sum()),
                         "fallos_total": int((~ok).sum()), "fallos_rechazados": int((~ok & ~acept).sum()),
                         "exactitud_conservadas": float(ok[acept].mean())}
    nll = lambda T: float(-np.mean(np.log(np.clip(con_temperatura(Pe, T)[np.arange(len(y)), y], 1e-12, 1))))
    Ts = np.round(np.arange(0.5, 5.01, 0.05), 2)
    T = float(Ts[np.argmin([nll(T) for T in Ts])])
    res["temperatura"] = {"T": T, "nll_antes": nll(1.0), "nll_despues": nll(T),
                          "ece_antes": ece(Pe, y), "ece_despues": ece(con_temperatura(Pe, T), y),
                          "umbral_msp_con_T": float(np.quantile(con_temperatura(Pe, T).max(1), 1 - RECALL_OBJETIVO))}
    json.dump(res, open(os.path.join(a.out, "calibracion.json"), "w"), indent=2, ensure_ascii=False)
    print(json.dumps(res, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
