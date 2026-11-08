"""Particiones train/val/test (enlaces simbólicos) de <origen>/<clase>/<imagen> SIN repartir al azar.

--modo bloques: dentro de cada clase y de cada grupo de nombre (lo que queda al quitar el número final: '2270_400x_17'
  → '2270_400x'), ordena por ese número y asigna el primer 70 % a train, el 20 % siguiente a val y el último 10 % a test.
  Las imágenes de un dataset se suelen tomar en secuencia: las vecinas son del mismo campo o espécimen y no deben
  quedar a ambos lados. Es lo más parecido a "por sesión" cuando el dataset no dice nada más.

  python particionar.py --origen DIR --destino DIR [--fracciones 0.7 0.2]
"""
import argparse, os, re
from collections import defaultdict

EXT = (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--origen", required=True)
    ap.add_argument("--destino", required=True)
    ap.add_argument("--fracciones", type=float, nargs=2, default=[0.7, 0.2])
    a = ap.parse_args()
    ftr, fva = a.fracciones
    resumen = defaultdict(lambda: defaultdict(int))
    for clase in sorted(os.listdir(a.origen)):
        d = os.path.join(a.origen, clase)
        if not os.path.isdir(d) or clase.startswith("."):
            continue
        grupos = defaultdict(list)
        for f in os.listdir(d):
            st, ext = os.path.splitext(f)
            if ext.lower() in EXT and not f.startswith("."):
                m = re.match(r"(.*?)[_-]?(\d+)$", st)
                grupos[m.group(1) if m else st].append((int(m.group(2)) if m else 0, f))
        for g, fs in grupos.items():
            fs.sort()
            n = len(fs)
            cortes = (round(n * ftr), round(n * (ftr + fva)))
            for i, (_, f) in enumerate(fs):
                split = "train" if i < cortes[0] else "val" if i < cortes[1] else "test"
                dd = os.path.join(a.destino, split, clase)
                os.makedirs(dd, exist_ok=True)
                dst = os.path.join(dd, f)
                if not os.path.lexists(dst):
                    os.symlink(os.path.abspath(os.path.join(d, f)), dst)
                resumen[clase][split] += 1
    for c, r in resumen.items():
        print(f"{c}: train {r['train']}, val {r['val']}, test {r['test']}")


if __name__ == "__main__":
    main()
