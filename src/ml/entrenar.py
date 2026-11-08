"""Entrena un clasificador de recortes para el PlanktoScope y deja el modelo con sus números (regla del repo: ningún
modelo sin su evaluación).

Dataset: <raiz>/<particion>/<clase>/<imagen>, con particion = train|training, val|validation, test.
Las particiones las decide quien construye el dataset: para el nuestro, POR SESIÓN (prepara_dataset.py); para uno
público sin sesiones, por bloques (particionar.py). Este script no reparte imágenes: EXCLUYE de val/test las que tienen
copia (md5) o casi-copia (dHash) en train, y lo deja anotado.

Modelo: MobileNetV3 Small o Large (ImageNet) + Dropout + Dense softmax. Fase 1: cabeza con la base congelada. Fase 2:
ajuste de toda la base (BatchNorm congelado) con parada temprana; si no mejora la exactitud de validación de la fase 1,
se queda la fase 1. Exporta TFLite (rango dinámico) y evalúa ESE fichero.
Preprocesado: Code/ml/preprocesado.a_cuadrado (el mismo fichero que usa la app), 224, 0-255 (la normalización va dentro
del modelo). modelo.json con las claves que lee Code/ml/classifier.py.

Nota: reescrito el 02/11/2026. La primera versión, con la que se entrenó modelos/lmfm12_mnv3s_bloques, se sobrescribió
por error; esta sigue sus convenciones (a_cuadrado, exclusión de fugas, lr de ajuste 1e-5, modelo.json).

  python entrenar.py --dataset DIR --out ../../modelos/NOMBRE [--arquitectura small|large] [--rapido]
  python entrenar.py --dataset DIR --out ../../modelos/NOMBRE --pesos-iniciales ../../modelos/lmfm12_mnv3s_bloques_repro/modelo.keras

Salida en --out: modelo.keras, modelo.tflite, modelo.json, metricas.json, confusion_test.png/.csv,
predicciones_test.csv, historial.csv y FICHA.md (con un apartado "Lo que estos números NO dicen" para rellenar a mano).
"""
import argparse, hashlib, json, os, time
import sys
import numpy as np
from PIL import Image
from evaluar_modelo import md5, dhash, hamming_min, UMBRAL_DHASH, EXT

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "Code"))
from ml.preprocesado import a_cuadrado  # el mismo fichero que usa la app en la Raspberry

TAM = 224

NOMBRES = {"train": ("train", "training"), "val": ("val", "validation"), "test": ("test",)}


def listar(raiz, particion):
    for nombre in NOMBRES[particion]:
        d = os.path.join(raiz, nombre)
        if os.path.isdir(d):
            return [(os.path.join(d, c, f), c) for c in sorted(os.listdir(d)) if os.path.isdir(os.path.join(d, c))
                    for f in sorted(os.listdir(os.path.join(d, c))) if f.lower().endswith(EXT) and not f.startswith(".")]
    raise SystemExit(f"No encuentro la partición '{particion}' ({' / '.join(NOMBRES[particion])}) en {raiz}")


def cargar(lista, cache):
    """Matriz uint8 (n, 224, 224, 3) en disco (memmap): se calcula una vez por lista de ficheros."""
    clave = hashlib.md5("\n".join(p for p, _ in lista).encode()).hexdigest()[:12]
    ruta = os.path.join(cache, f"{clave}.npy")
    if os.path.exists(ruta):
        return np.load(ruta, mmap_mode="r")
    X = np.lib.format.open_memmap(ruta + ".tmp.npy", mode="w+", dtype=np.uint8, shape=(len(lista), TAM, TAM, 3))
    for i, (p, _) in enumerate(lista):
        X[i] = a_cuadrado(np.asarray(Image.open(p).convert("RGB")), TAM)
    X.flush(); del X
    os.replace(ruta + ".tmp.npy", ruta)
    return np.load(ruta, mmap_mode="r")


def sin_fugas(train, otros):
    """Quita de 'otros' lo que tiene copia exacta (md5) o casi-copia (dHash) en train; devuelve (limpios, nº quitadas)."""
    md5_tr = {md5(p) for p, _ in train}
    dh_tr = np.array([dhash(p) for p, _ in train], dtype=np.uint64)
    limpios = [(p, c) for p, c in otros if md5(p) not in md5_tr and hamming_min(dhash(p), dh_tr) > UMBRAL_DHASH]
    return limpios, len(otros) - len(limpios)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--epocas-cabeza", type=int, default=5)
    ap.add_argument("--epocas-ajuste", type=int, default=20)
    ap.add_argument("--batch", type=int, default=32)
    ap.add_argument("--arquitectura", choices=["small", "large"], default="small")
    ap.add_argument("--lr-ajuste", type=float, default=1e-5)
    ap.add_argument("--dropout", type=float, default=0.2)
    ap.add_argument("--pesos-iniciales", help="modelo.keras previo (p. ej. el de LMFM-12): se reutiliza su base ya "
                                              "ajustada a algas en lugar de la de ImageNet; la cabeza se crea nueva")
    ap.add_argument("--rapido", action="store_true", help="20 imágenes por clase y 1+1 épocas: solo prueba el pipeline")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    cache = os.path.join(os.path.expanduser("~/datasets"), "cache_a_cuadrado"); os.makedirs(cache, exist_ok=True)

    import tensorflow as tf, keras
    from sklearn.metrics import classification_report, confusion_matrix, balanced_accuracy_score
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    keras.utils.set_random_seed(0)

    part = {k: listar(a.dataset, k) for k in NOMBRES}
    if a.rapido:
        part = {k: [x for c in sorted({c for _, c in v}) for x in [y for y in v if y[1] == c][:20]] for k, v in part.items()}
        a.epocas_cabeza = a.epocas_ajuste = 1
    clases = sorted({c for _, c in part["train"]})
    for k, v in part.items():
        ajenas = {c for _, c in v} - set(clases)
        if ajenas:
            raise SystemExit(f"{k} tiene clases que no están en train: {ajenas}")
    print("Quitando de val/test las copias de train...", flush=True)
    fuga = {}
    for k in ("val", "test"):
        n0 = len(part[k])
        part[k], fuga[k] = sin_fugas(part["train"], part[k])
        fuga[k] = {"excluidas": fuga[k], "de": n0}
    print(fuga, flush=True)

    X = {k: cargar(v, cache) for k, v in part.items()}
    y = {k: np.array([clases.index(c) for _, c in v]) for k, v in part.items()}
    cuenta = {k: {c: int((y[k] == i).sum()) for i, c in enumerate(clases)} for k in part}
    pesos = {i: len(y["train"]) / (len(clases) * max(1, n)) for i, n in enumerate(cuenta["train"].values())}

    aumento = keras.Sequential([keras.layers.RandomFlip("horizontal_and_vertical"),
                                keras.layers.RandomRotation(0.5, fill_mode="reflect"),
                                keras.layers.RandomZoom(0.1, fill_mode="reflect"),
                                keras.layers.RandomBrightness(0.15, value_range=(0, 255)),
                                keras.layers.RandomContrast(0.15)])

    class Lotes(keras.utils.PyDataset):
        """Lotes desde el memmap (no carga el dataset entero en memoria), con aumento y peso por clase en train."""
        def __init__(self, k, entrenar):
            super().__init__()
            self.k, self.entrenar = k, entrenar
            self.orden = np.arange(len(y[k]))
            self.w = np.array([pesos[i] for i in range(len(clases))], np.float32)
            self.on_epoch_end()

        def __len__(self):
            return int(np.ceil(len(self.orden) / a.batch))

        def __getitem__(self, b):
            idx = np.sort(self.orden[b * a.batch:(b + 1) * a.batch])
            xb, yb = X[self.k][idx].astype(np.float32), y[self.k][idx]
            if not self.entrenar:
                return xb, yb
            return keras.ops.convert_to_numpy(aumento(xb, training=True)), yb, self.w[yb]

        def on_epoch_end(self):
            if self.entrenar:
                np.random.default_rng().shuffle(self.orden)

    flujo = Lotes

    if a.pesos_iniciales:
        previo = keras.models.load_model(a.pesos_iniciales)
        base = next(l for l in previo.layers if isinstance(l, keras.Model))   # la MobileNetV3 dentro del modelo previo
        arquitectura = f"{base.name} desde {os.path.basename(os.path.dirname(os.path.abspath(a.pesos_iniciales)))}"
    else:
        Base = keras.applications.MobileNetV3Small if a.arquitectura == "small" else keras.applications.MobileNetV3Large
        arquitectura = Base.__name__
        base = Base(input_shape=(TAM, TAM, 3), include_top=False, weights="imagenet", pooling="avg", include_preprocessing=True)
    base.trainable = False
    ent = keras.Input((TAM, TAM, 3))
    sal = keras.layers.Dense(len(clases), activation="softmax")(keras.layers.Dropout(a.dropout)(base(ent, training=False)))
    modelo = keras.Model(ent, sal)
    hist = []
    modelo.compile(optimizer=keras.optimizers.Adam(1e-3), loss="sparse_categorical_crossentropy", metrics=["accuracy"])
    h = modelo.fit(flujo("train", True), validation_data=flujo("val", False), epochs=a.epocas_cabeza, verbose=2)
    hist += [{"fase": "cabeza", **{k: float(v[i]) for k, v in h.history.items()}} for i in range(len(h.history["loss"]))]
    acc_cabeza = modelo.evaluate(flujo("val", False), verbose=0)[1]
    pesos_cabeza = modelo.get_weights()

    base.trainable = True
    for capa in base.layers:
        if isinstance(capa, keras.layers.BatchNormalization):
            capa.trainable = False   # con lotes pequeños, reentrenar BatchNorm estropea lo aprendido en ImageNet
    modelo.compile(optimizer=keras.optimizers.Adam(a.lr_ajuste), loss="sparse_categorical_crossentropy", metrics=["accuracy"])
    cbs = [keras.callbacks.EarlyStopping(patience=4, restore_best_weights=True),
           keras.callbacks.ReduceLROnPlateau(factor=0.3, patience=2)]
    h = modelo.fit(flujo("train", True), validation_data=flujo("val", False), epochs=a.epocas_ajuste,
                   callbacks=cbs, verbose=2)
    hist += [{"fase": "ajuste", **{k: float(v[i]) for k, v in h.history.items()}} for i in range(len(h.history["loss"]))]
    acc_ajuste = modelo.evaluate(flujo("val", False), verbose=0)[1]
    ajuste_usado = acc_ajuste >= acc_cabeza
    if not ajuste_usado:
        modelo.set_weights(pesos_cabeza)
    print(f"val: cabeza {acc_cabeza:.3f}, ajuste {acc_ajuste:.3f} -> {'ajuste' if ajuste_usado else 'cabeza'}", flush=True)
    modelo.save(os.path.join(a.out, "modelo.keras"))

    conv = tf.lite.TFLiteConverter.from_keras_model(modelo)
    conv.optimizations = [tf.lite.Optimize.DEFAULT]
    ruta_tfl = os.path.join(a.out, "modelo.tflite")
    open(ruta_tfl, "wb").write(conv.convert())

    # Evaluación SIEMPRE con el .tflite (lo que correrá en la Raspberry), no con el modelo de Keras
    it = tf.lite.Interpreter(model_path=ruta_tfl); it.allocate_tensors()
    i_in, i_out = it.get_input_details()[0], it.get_output_details()[0]

    def predecir(k):
        P, t0 = [], time.time()
        for x in X[k]:
            it.set_tensor(i_in["index"], x[None].astype(np.float32)); it.invoke()
            P.append(it.get_tensor(i_out["index"])[0])
        return np.array(P), (time.time() - t0) / max(1, len(X[k]))

    Pv, _ = predecir("val")
    Pt, seg = predecir("test")
    umbral = float(np.quantile(Pv.max(1), 0.05))   # conserva el 95 % de las de clases conocidas en validación
    yt, yh = y["test"], Pt.argmax(1)
    rng = np.random.default_rng(0)
    boot = [np.mean((yt == yh)[rng.integers(0, len(yt), len(yt))]) for _ in range(2000)]
    rep = classification_report(yt, yh, labels=range(len(clases)), target_names=clases, zero_division=0, output_dict=True)
    acept = Pt.max(1) >= umbral
    met = {"dataset": os.path.abspath(a.dataset), "clases": clases, "imagenes": cuenta, "fugas": fuga,
           "test": {"n": int(len(yt)), "exactitud": float(np.mean(yt == yh)),
                    "exactitud_ic95": [float(np.quantile(boot, 0.025)), float(np.quantile(boot, 0.975))],
                    "exactitud_balanceada": float(balanced_accuracy_score(yt, yh)),
                    "por_clase": {c: {k: round(rep[c][k], 4) for k in ("precision", "recall", "f1-score", "support")} for c in clases}},
           "umbral_confianza": {"valor": umbral, "criterio": "cuantil 5 % de la confianza máxima en validación",
                                "test_conservadas": float(acept.mean()), "test_exactitud_conservadas": float(np.mean((yt == yh)[acept]))},
           "tflite": {"md5": md5(ruta_tfl), "bytes": os.path.getsize(ruta_tfl), "ms_por_imagen_mac": round(seg * 1000, 1)},
           "entrenamiento": {"base": arquitectura if a.pesos_iniciales else f"{arquitectura} ImageNet",
                             "pesos_iniciales": a.pesos_iniciales, "val_acc_cabeza": float(acc_cabeza),
                             "val_acc_ajuste": float(acc_ajuste), "ajuste_usado": bool(ajuste_usado), "lr_ajuste": a.lr_ajuste, "epocas_cabeza": a.epocas_cabeza, "epocas_ajuste_max": a.epocas_ajuste,
                             "epocas_ajuste_hechas": sum(1 for r in hist if r["fase"] == "ajuste"), "batch": a.batch, "rapido": a.rapido}}
    json.dump(met, open(os.path.join(a.out, "metricas.json"), "w"), indent=2, ensure_ascii=False)
    json.dump({"clases": clases, "lado": TAM, "preprocesado": "a_cuadrado", "escala": "0-255", "umbral_msp": umbral,
               "arquitectura": arquitectura, "md5_tflite": met["tflite"]["md5"]},
              open(os.path.join(a.out, "modelo.json"), "w"), indent=2, ensure_ascii=False)
    with open(os.path.join(a.out, "historial.csv"), "w") as fh:
        campos = sorted({k for r in hist for k in r})
        fh.write(",".join(campos) + "\n")
        for r in hist:
            fh.write(",".join(str(r.get(k, "")) for k in campos) + "\n")
    with open(os.path.join(a.out, "predicciones_test.csv"), "w") as fh:
        fh.write("imagen,real,predicho,confianza\n")
        for (p, c), k, s in zip(part["test"], yh, Pt.max(1)):
            fh.write(f"\"{os.path.relpath(p, a.dataset)}\",{c},{clases[k]},{s:.4f}\n")
    cm = confusion_matrix(yt, yh, labels=range(len(clases)))
    np.savetxt(os.path.join(a.out, "confusion_test.csv"), cm, fmt="%d", delimiter=",", header=",".join(clases), comments="")
    fig, ax = plt.subplots(figsize=(10, 9))
    ax.imshow(cm, cmap="Blues"); ax.set_xticks(range(len(clases)), clases, rotation=90, fontsize=8)
    ax.set_yticks(range(len(clases)), clases, fontsize=8); ax.set_xlabel("predicho"); ax.set_ylabel("real")
    for r in range(len(clases)):
        for k in range(len(clases)):
            if cm[r, k]: ax.text(k, r, cm[r, k], ha="center", va="center", fontsize=7)
    ax.set_title(f"test: n={len(yt)}, exactitud={met['test']['exactitud']:.3f}")
    fig.tight_layout(); fig.savefig(os.path.join(a.out, "confusion_test.png"), dpi=120); plt.close(fig)

    t, f = met["test"], met["fugas"]
    filas = "\n".join(f"| {c} | {cuenta['train'][c]} | {cuenta['val'][c]} | {cuenta['test'][c]} | {t['por_clase'][c]['precision']:.3f} | "
                      f"{t['por_clase'][c]['recall']:.3f} |" for c in clases)
    open(os.path.join(a.out, "FICHA.md"), "w").write(f"""# Ficha — {os.path.basename(os.path.abspath(a.out))}

Generada por `src/ml/entrenar.py` el {time.strftime('%d/%m/%Y')}. Métricas completas en `metricas.json`.
{"**EJECUCIÓN RÁPIDA DE PRUEBA (--rapido): los números no valen nada.**" if a.rapido else ""}

| | |
|---|---|
| Dataset | `{met['dataset']}` |
| Modelo | {arquitectura}{"" if a.pesos_iniciales else " (ImageNet)"} + Dropout {a.dropout} + Dense {len(clases)}; cabeza {a.epocas_cabeza} épocas (val {acc_cabeza:.3f}), ajuste {met['entrenamiento']['epocas_ajuste_hechas']} épocas con lr {a.lr_ajuste} (val {acc_ajuste:.3f}); se usa: {'ajuste' if ajuste_usado else 'cabeza'} |
| Preprocesado | `Code/ml/preprocesado.a_cuadrado`, 224, 0-255 (ver `modelo.json`) |
| TFLite | `modelo.tflite`, md5 `{met['tflite']['md5']}`, {met['tflite']['bytes'] / 1e6:.1f} MB, {met['tflite']['ms_por_imagen_mac']} ms/imagen en el Mac |

## Copias entre particiones (excluidas antes de evaluar)

- val: {f['val']['excluidas']} de {f['val']['de']} tenían copia exacta o casi-copia (dHash ≤ {UMBRAL_DHASH}) en train
- test: {f['test']['excluidas']} de {f['test']['de']}

## Números (test, evaluado con el .tflite)

- **Exactitud {t['exactitud']:.3f}** (IC95 % bootstrap {t['exactitud_ic95'][0]:.3f}–{t['exactitud_ic95'][1]:.3f}), exactitud balanceada {t['exactitud_balanceada']:.3f}, n = {t['n']}
- **Umbral de confianza** {umbral:.3f} (conserva el 95 % en validación): en test conserva el {met['umbral_confianza']['test_conservadas']:.1%} con exactitud {met['umbral_confianza']['test_exactitud_conservadas']:.3f}

| Clase | train | val | test | precisión | recall |
|---|---|---|---|---|---|
{filas}

## Lo que estos números NO dicen (rellenar a mano)

- ¿Las particiones están separadas por sesión/cultivo o son un reparto aleatorio de imágenes?
- ¿Las imágenes son del PlanktoScope (óptica, cámara, capilar) o de otro microscopio?
- ¿Cómo se comporta con objetos que no son de estas clases?
""")
    print(json.dumps({k: met[k] for k in ("test", "umbral_confianza", "tflite")}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
