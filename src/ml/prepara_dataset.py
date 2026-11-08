"""Dataset propio → <destino>/{train,val,test}/<clase>/ (enlaces simbólicos) con particiones POR SESIÓN.

Etiquetas, de una de dos fuentes:
  --ecotaxa TSV   exportación de EcoTaxa: object_id (= nombre del recorte sin .png) y object_annotation_category;
                  solo se usan las filas con object_annotation_status = validated
  --carpetas DIR  <DIR>/<clase>/<recorte>.png, ordenadas a mano
Sesión de cada recorte: el número de foto al principio del nombre ('12_capa-205_3.png' → foto 12), buscado en
datos/sesiones.csv (fotos_desde–fotos_hasta). La partición la decide la columna 'particion' de sesiones.csv
(train/val/test), que se rellena ANTES de entrenar (protocolo §6). La clase 'duda' no se usa.

  python prepara_dataset.py --recortes samples/recortes --carpetas etiquetados/ --sesiones datos/sesiones.csv --destino DIR
"""
import argparse, csv, os, re, sys
from collections import Counter, defaultdict


def leer_sesiones(ruta):
    ses = []
    for r in csv.DictReader(open(ruta, newline="")):
        if r.get("particion") not in ("train", "val", "test"):
            sys.exit(f"sesiones.csv: la sesión {r.get('sesion')} no tiene particion train/val/test")
        ses.append((int(r["fotos_desde"]), int(r["fotos_hasta"]), r["sesion"], r["particion"]))
    return ses


def sesion_de(nombre, sesiones):
    m = re.match(r"(\d+)", os.path.basename(nombre))
    n = int(m.group(1)) if m else -1
    for desde, hasta, s, p in sesiones:
        if desde <= n <= hasta:
            return s, p
    return None, None


def etiquetas(a):
    if a.ecotaxa:
        lector = csv.DictReader(open(a.ecotaxa, newline=""), delimiter="\t")
        for r in lector:
            if r.get("object_annotation_status") == "validated" and r.get("object_annotation_category"):
                yield os.path.join(a.recortes, r["object_id"] + ".png"), r["object_annotation_category"]
    else:
        for clase in sorted(os.listdir(a.carpetas)):
            d = os.path.join(a.carpetas, clase)
            if os.path.isdir(d):
                for f in sorted(os.listdir(d)):
                    if f.lower().endswith(".png"):
                        yield os.path.join(d, f), clase


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--recortes", required=True)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--ecotaxa")
    g.add_argument("--carpetas")
    ap.add_argument("--sesiones", required=True)
    ap.add_argument("--destino", required=True)
    a = ap.parse_args()
    sesiones = leer_sesiones(a.sesiones)
    cuenta, sin_sesion, ses_por_clase = Counter(), [], defaultdict(set)
    for ruta, clase in etiquetas(a):
        if clase == "duda":
            continue
        s, part = sesion_de(ruta, sesiones)
        if s is None or not os.path.exists(ruta):
            sin_sesion.append(ruta); continue
        d = os.path.join(a.destino, part, clase)
        os.makedirs(d, exist_ok=True)
        dst = os.path.join(d, os.path.basename(ruta))
        if not os.path.lexists(dst):
            os.symlink(os.path.abspath(ruta), dst)
        cuenta[(part, clase)] += 1
        ses_por_clase[(part, clase)].add(s)
    clases = sorted({c for _, c in cuenta})
    print(f"{'clase':24s} {'train':>12s} {'val':>12s} {'test':>12s}")
    for c in clases:
        print(f"{c:24s} " + " ".join(f"{cuenta[(p, c)]:6d} ({len(ses_por_clase[(p, c)])} s)" for p in ("train", "val", "test")))
    faltan = [f"{c}/{p}" for c in clases for p in ("train", "val", "test") if not cuenta[(p, c)]]
    if faltan:
        print("AVISO: sin recortes en", ", ".join(faltan))
    if sin_sesion:
        print(f"AVISO: {len(sin_sesion)} recortes sin sesión en sesiones.csv o sin fichero (p. ej. {sin_sesion[0]})")
    return cuenta


if __name__ == "__main__":
    main()
