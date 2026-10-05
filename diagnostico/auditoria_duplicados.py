"""Busca imágenes idénticas (MD5 del fichero) entre training / validation / test de un conjunto
organizado como <raiz>/<split>/<clase>/<imagen>. Solo detecta copias exactas: recortes, reescalados
o recompresiones de la misma imagen NO se detectan, así que la fuga real puede ser mayor.

    python3 auditoria_duplicados.py ".../ml_plankton/dataset_pm"
"""
import collections, hashlib, os, sys

raiz = sys.argv[1]
splits = ["training", "validation", "test"]
EXT = (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp")
por_hash = collections.defaultdict(list)
for sp in splits:
    for cls in sorted(os.listdir(os.path.join(raiz, sp))):
        d = os.path.join(raiz, sp, cls)
        if not os.path.isdir(d):
            continue
        for f in os.listdir(d):
            p = os.path.join(d, f)
            if f.startswith(".") or not os.path.isfile(p) or not f.lower().endswith(EXT):
                continue  # descarta desktop.ini, .DS_Store, etc.
            with open(p, "rb") as fh:
                por_hash[hashlib.md5(fh.read()).hexdigest()].append((sp, cls, f))

n = collections.Counter(sp for v in por_hash.values() for sp, _, _ in v)
print("ficheros por split:", dict(n), "| hashes únicos en total:", len(por_hash))
dup_train = sum(max(0, sum(1 for x in v if x[0] == "training") - 1) for v in por_hash.values())
print(f"training: {dup_train} copias exactas dentro del propio training -> {n['training'] - dup_train} imágenes únicas")
multi = [v for v in por_hash.values() if len({c for _, c, _ in v}) > 1]
print("imágenes idénticas con más de una etiqueta:", len(multi))
for v in multi:
    print("   ", v)
for sp in ("validation", "test"):
    fuga = collections.Counter()
    for v in por_hash.values():
        if any(x[0] == "training" for x in v):
            for s, c, _ in v:
                if s == sp:
                    fuga[c] += 1
    print(f"{sp}: {sum(fuga.values())}/{n[sp]} imágenes están también en training")
    print("    por clase:", dict(sorted(fuga.items())))
tv = sum(1 for v in por_hash.values() if {"test", "validation"} <= {x[0] for x in v})
print("hashes compartidos test-validation:", tv)
