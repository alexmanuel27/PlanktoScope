"""Auditoría de un clasificador .tflite sobre un conjunto <raiz>/<split>/<clase>/<imagen>.

Evalúa en tres subconjuntos y deja todo en --out:
  test_original  el test tal cual (como se habría reportado)
  limpio         test + validation SIN copias exactas (md5) NI casi-copias (dHash <= UMBRAL_DHASH)
                 de ninguna imagen de training, y sin repetidos entre sí
  (simulación)   qué habría mostrado la app si usa una lista de etiquetas distinta (--labels-app)

Preprocesado idéntico al de train.py: keras load_img (RGB, 224x224, interpolación 'nearest') y /255.

  python evaluar_modelo.py --modelo m.tflite --labels labels.json --dataset dataset_pm --out salida/ \
      [--labels-app Ceratium Copepod Diatom Dinoflagellate Other]
"""
import argparse, hashlib, json, os
import numpy as np
from PIL import Image

UMBRAL_DHASH = 5  # ponytail: umbral heurístico (bits de 64); revisar a ojo los pares en limite si cambia el resultado
EXT = (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp")


def imagenes(raiz, split):
    for cls in sorted(os.listdir(os.path.join(raiz, split))):
        d = os.path.join(raiz, split, cls)
        if os.path.isdir(d):
            for f in sorted(os.listdir(d)):
                if f.lower().endswith(EXT) and not f.startswith("."):
                    yield os.path.join(d, f), cls


def md5(p):
    with open(p, "rb") as fh:
        return hashlib.md5(fh.read()).hexdigest()


def dhash(p):
    a = np.asarray(Image.open(p).convert("L").resize((9, 8), Image.LANCZOS), dtype=np.int16)
    return np.packbits((a[:, 1:] > a[:, :-1]).ravel()).view(">u8")[0]


def hamming_min(h, banco):
    x = np.bitwise_xor(banco, np.uint64(h)).view(np.uint8)
    return int(np.unpackbits(x).reshape(len(banco), 64).sum(1).min())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--modelo", required=True)
    ap.add_argument("--labels", required=True)
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--labels-app", nargs="*")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    import tensorflow as tf
    from keras.utils import load_img
    from sklearn.metrics import classification_report, confusion_matrix
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt

    idx = json.load(open(a.labels))
    clases = [c for c, _ in sorted(idx.items(), key=lambda kv: kv[1])]

    train = list(imagenes(a.dataset, "training"))
    md5_train = {md5(p) for p, _ in train}
    dh_train = np.array([dhash(p) for p, _ in train], dtype=np.uint64)

    vistos, limpio, fugas = set(), [], {"exacta": 0, "casi": 0, "repetida": 0}
    dist_limpio = []
    for split in ("test", "validation"):
        for p, c in imagenes(a.dataset, split):
            h = md5(p)
            if h in md5_train: fugas["exacta"] += 1; continue
            if h in vistos: fugas["repetida"] += 1; continue
            d = hamming_min(dhash(p), dh_train)
            if d <= UMBRAL_DHASH: fugas["casi"] += 1; continue
            vistos.add(h); limpio.append((p, c)); dist_limpio.append(d)

    it = tf.lite.Interpreter(model_path=a.modelo); it.allocate_tensors()
    i_in, i_out = it.get_input_details()[0], it.get_output_details()[0]
    size = tuple(i_in["shape"][1:3])

    def predecir(lista):
        out = []
        for p, _ in lista:
            x = np.asarray(load_img(p, target_size=size), dtype=np.float32)[None] / 255.0
            it.set_tensor(i_in["index"], x); it.invoke()
            out.append(it.get_tensor(i_out["index"])[0])
        return np.array(out)

    resumen = {"modelo": a.modelo, "md5_modelo": md5(a.modelo), "salidas": int(i_out["shape"][-1]),
               "clases": clases, "umbral_dhash": UMBRAL_DHASH, "descartadas_de_test+val": fugas,
               "n_training": len(train), "subconjuntos": {}}
    for nombre, lista in (("test_original", list(imagenes(a.dataset, "test"))), ("limpio", limpio)):
        if not lista:
            continue
        P = predecir(lista)
        y = np.array([clases.index(c) for _, c in lista]); yh = P.argmax(1)
        conf = P.max(1); top3 = np.mean([y[k] in np.argsort(P[k])[-3:] for k in range(len(y))])
        rep = classification_report(y, yh, labels=range(len(clases)), target_names=clases,
                                    zero_division=0, output_dict=True)
        cm = confusion_matrix(y, yh, labels=range(len(clases)))
        np.savetxt(os.path.join(a.out, f"confusion_{nombre}.csv"), cm, fmt="%d", delimiter=",",
                   header=",".join(clases), comments="")
        fig, ax = plt.subplots(figsize=(11, 10))
        ax.imshow(cm, cmap="Blues"); ax.set_xticks(range(len(clases)), clases, rotation=90, fontsize=8)
        ax.set_yticks(range(len(clases)), clases, fontsize=8); ax.set_xlabel("predicho"); ax.set_ylabel("real")
        for r in range(len(clases)):
            for k in range(len(clases)):
                if cm[r, k]: ax.text(k, r, cm[r, k], ha="center", va="center", fontsize=7)
        ax.set_title(f"{nombre}: n={len(y)}, exactitud={np.mean(y == yh):.3f}")
        fig.tight_layout(); fig.savefig(os.path.join(a.out, f"confusion_{nombre}.png"), dpi=120); plt.close(fig)
        with open(os.path.join(a.out, f"predicciones_{nombre}.csv"), "w") as fh:
            fh.write("imagen,real,predicho,confianza\n")
            for (p, c), k, s in zip(lista, yh, conf):
                fh.write(f"\"{os.path.relpath(p, a.dataset)}\",{c},{clases[k]},{s:.4f}\n")
        r = {"n": int(len(y)), "exactitud": float(np.mean(y == yh)), "top3": float(top3),
             "f1_macro_clases_presentes": float(np.mean([rep[c]["f1-score"] for c in clases if rep[c]["support"]])),
             "confianza_media_aciertos": float(conf[y == yh].mean()) if (y == yh).any() else None,
             "confianza_media_fallos": float(conf[y != yh].mean()) if (y != yh).any() else None,
             "por_clase": {c: {k: rep[c][k] for k in ("precision", "recall", "f1-score", "support")} for c in clases}}
        if a.labels_app:
            n = len(a.labels_app)
            r["app"] = {"labels_app": a.labels_app,
                        "fraccion_error_indice": float(np.mean(yh >= n)),
                        "fraccion_nombre_correcto": float(np.mean([k < n and a.labels_app[k] == clases[t] for k, t in zip(yh, y)]))}
        resumen["subconjuntos"][nombre] = r
    if dist_limpio:
        resumen["dhash_min_limpio"] = {"min": min(dist_limpio), "mediana": float(np.median(dist_limpio))}
    json.dump(resumen, open(os.path.join(a.out, "metricas.json"), "w"), indent=2, ensure_ascii=False)
    for n, r in resumen["subconjuntos"].items():
        print(f"{n}: n={r['n']} exactitud={r['exactitud']:.3f} top3={r['top3']:.3f} F1macro={r['f1_macro_clases_presentes']:.3f}"
              + (f" | app: error_indice={r['app']['fraccion_error_indice']:.2f} nombre_ok={r['app']['fraccion_nombre_correcto']:.2f}" if "app" in r else ""))
    print("descartadas:", fugas, "| limpio:", len(limpio))


if __name__ == "__main__":
    main()
