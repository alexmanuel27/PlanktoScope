# Fuentes de datos para el clasificador

Revisado el 27/09/2026. Las licencias se han leído en la página de cada depósito; hay que confirmarlas en el
fichero LICENSE del paquete descargado antes de usar cualquier conjunto en el artículo.

## 1. Origen de `dataset_pm` (el conjunto del modelo actual) — IDENTIFICADO

**Kaggle `feruzz/plankton-dataset`** — "Plankton Dataset", autor "Pheonix", versión única del 26/05/2022, 7,2 GB,
**licencia "Unknown"**. https://www.kaggle.com/datasets/feruzz/plankton-dataset

Coincidencias verificadas con la API de Kaggle:

- La carpeta raíz se llama literalmente `dataset_pm/`.
- Las mismas 19 clases.
- La misma fecha de los ficheros (26/05/2022).
- Los mismos `desktop.ini` de Google Drive en cada carpeta.

Descripción del autor, textual: *"derived from internet images, course-given images, and WHOI plankton dataset"*,
3.144 imágenes, reparto 80/10/10.

Lo que implica:

- **No se puede usar en el artículo ni redistribuir.** No tiene licencia, y parte son imágenes de internet y de un
  curso con derechos desconocidos.
- **Mezcla de fuentes por clase** (comprobado en los ficheros; ejemplo en `dataset_pm_mezcla_de_fuentes.jpg`):
  - 8 clases son casi solo fotos de microscopio en color de 2448×2448: Alexandrium, Nitzschia, Noctiluca,
    Ornithocercus, Pinnularia, Protoperidinium, Pyrodinium y Thalassionema.
  - Cada una sale de 4 a 19 fotos originales, que se multiplican hasta ~150 con copias aumentadas
    (`augmented_image_*`).
  - El resto son sobre todo recortes en gris de IFCB (WHOI).
  - El modelo puede acertar la clase por el *tipo de imagen* y no por el organismo.
- **El test local no es el de Kaggle.**
  - En Kaggle, `test/Ceratium` contiene `3_0 … 3_14.png` (15 imágenes propias).
  - La copia local contiene `4_0 … 4_11.png`, copias de training, y la carpeta es del 14/12/2025.
  - La fuga del test se introdujo al reorganizar en local.

## 2. Candidatos

Para qué nos puede servir cada uno:

- **D**: dominio PlanktoScope (preentrenar o ajustar con imágenes del mismo instrumento).
- **N**: clases "no alga" (detrito, burbuja, fibra) para K3.4.
- **O**: taxones ajenos para evaluar el rechazo (*open-set*) en K3.6.
- **A**: fitoplancton de agua dulce.

| Conjunto | Instrumento | Medio | Tamaño | Licencia | Uso | Pega principal |
|---|---|---|---|---|---|---|
| [PlanktoScope_reference](https://www.seanoe.org/data/00989/110078/) (Zaccomer, Lombard et al., 2025; DOI 10.17882/110078) | **PlanktoScope** | marino | 169.149 objetos, 256 taxones, validados en EcoTaxa | CC BY-NC 4.0 | **D, N**, O | marino; talla de red (20–300 µm) |
| [Lac du Luitel](https://ecotaxa.obs-vlfr.fr/prj/4461) (EcoTaxa 4461, GBIF 10.15468/xegphg; S. Rafaï, CNRS) | **PlanktoScope** | **agua dulce** (lago alpino) | 36.691 validados de 175.930 | CC BY-NC 4.0 (según GBIF) | **D, A, O, N** | solo un lago; hay que revisar clases y validación |
| [PlanktonLake-CEREEP](https://zenodo.org/records/22012197) (Déchaumet et al., 2026) | FlowCAM 8000 | **agua dulce** (16 estanques experimentales, Francia) | ~88.000 imágenes, 43 taxones incl. detrito | **CC BY 4.0** | **A, N, O** | FlowCAM, no PlanktoScope; más zooplancton que fitoplancton pequeño |
| [ZooLake](https://doi.org/10.25678/0004DY) (Kyathanahally et al., 2021, Eawag) | DSPC (cámara in situ) | agua dulce (Greifensee) | 17.943 imágenes, 35 clases (dinobryon, cianobacterias, *dirt*, *unknown*…) | no consta en la ficha; confirmar | O, N | óptica muy distinta; sobre todo zooplancton |
| [SYKE-plankton_IFCB_2025](https://zenodo.org/records/17601020) (Kraft et al., 2025) | IFCB | Báltico (salobre) | ~71.000 imágenes, 152 clases (Aphanizomenon, Dolichospermum, Scenedesmus, Monoraphidium…) | **CC BY 4.0** | O, parte A | IFCB en gris; salobre |
| [FMPD](https://zenodo.org/records/11126643) (Rivas-Villar, Figueroa et al., 2024, U. Coruña) | microscopio óptico, color, 10× | **agua dulce** (Doniños, Galicia) | 293 imágenes, 645 ejemplares: Woronichinia, Anabaena, Dinobryon, "otro fitoplancton", "no fitoplancton" | CC BY-NC-ND 4.0 | **O** (evaluación) | pequeño; ND impide publicar versiones modificadas |
| [LMFM-12](https://doi.org/10.5281/zenodo.17669912) (Hussin et al., 2026) | microscopio óptico 400×/1000× | agua dulce, **cultivos** NIES | 7.555 imágenes, 12 especies (Scenedesmus, Pediastrum, Closterium…) | **CC BY 4.0** | A, O | aumento mucho mayor que el nuestro; cultivos, no campo |
| [WHOI-Plankton](https://github.com/hsosik/WHOI-Plankton) (Sosik et al.) | IFCB | marino | >3,5 M imágenes, 103 clases | código MIT; confirmar la de los datos en el DOI 10.1575/1912/7341 | O, N | marino, en gris; es la parte "limpia" de `dataset_pm` |
| [PMID2019](https://github.com/ouc-ocean-group/PMID2019) (Li et al., 2020) | Olympus BX53 200×, color | marino (bahía de Jiaozhou), fijado con formol | 10.819 imágenes, 24 clases, cajas | no consta | O | marino; es de detección, no de clasificación |
| [Diatom Dataset](https://www.kaggle.com/datasets/huseyingunduz/diatom-dataset) (Gündüz et al., 2022) | microscopio, color | diatomeas | 2.197 imágenes, 68 especies | CC BY-NC-SA 4.0 | O | diatomeas preparadas, no vivas |
| [UDE Diatoms in the Wild 2024](https://academic.oup.com/gigascience/article/doi/10.1093/gigascience/giae087/7912108) | escáner de portas 60× | agua dulce | 83.570 imágenes, 611 taxones | CC BY | — | frústulos limpiados; otra escala y otra preparación |
| [The algae cell images](https://www.kaggle.com/datasets/mengyuy/the-algae-cell-images) (Kaggle, 2021) | microscopio | agua dulce (cianobacterias nocivas) | ~11 géneros × 150 (con aumentadas) | **Unknown** | — | mismo problema que `dataset_pm` |

## 3. Qué haría con esto (propuesta, no decidida)

1. **Retirar `dataset_pm` como base del artículo.** Como mucho, sirve de prueba del *pipeline*.
2. **El entrenamiento principal son nuestras capturas** (K4.4). Ningún conjunto público trae nuestras cepas vistas
   con nuestro PlanktoScope.
3. **Imágenes de PlanktoScope de otros** (PlanktoScope_reference y Lac du Luitel), para dos cosas:
   - las clases "no alga" (detrito, burbuja, fibra), que están en el mismo instrumento y ahorran etiquetar (K3.4);
   - preentrenar el extractor en el aspecto de este instrumento.
   - Ambos son NC: vale para investigación, pero hay que citarlos y no usarlos comercialmente.
4. **Evaluar el rechazo de taxones ajenos (K3.6)** con agua dulce de licencia clara: CEREEP (estanques, CC BY) y,
   solo para evaluar, FMPD. Complementa, no sustituye, las muestras de los lagos de Bruselas.
5. **Qué conjunto sirve para qué clases depende de las especies compradas en K4.1**, que no conozco.

La literatura respalda la preocupación por el cambio de dominio: en Greifensee, un MobileNet con 92 % dentro del
conjunto cae al 77 % en fechas no vistas ([Chen et al.](https://ar5iv.labs.arxiv.org/html/2401.14256)). Hodač et
al. (2025, *L&O Methods*, [doi](https://doi.org/10.1002/lom3.10723)) estudian justo nuestro caso: entrenar con
cepas y clasificar muestras de campo. Su contenido no se ha podido leer (acceso bloqueado); hay que leerlo antes
del 15/10.
