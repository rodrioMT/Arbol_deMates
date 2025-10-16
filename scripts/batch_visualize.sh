#!/usr/bin/env bash
set -euo pipefail

# EU RODRIGO! Sí funciona la madre.
# Ahora mi pregunta es... tipo... es q cada cosita es pequeña,
# creo que todo junto es como 3-5 MB entonces digo...
# Si tenemos 100 PDFs, ya es 300-500 MB, eso no es nada.
# Entonces lo que creo que podemos hacer ahora es darle un 
# Nombre a cada imagen! y si hay demasiada perdida de resoución,
# entonces guardar coordenadas, pero de momento esta bien. 
# Me gustaría más ponerle un nombre a cada imagen, tipo
# EX_Adm_UNI_2025_2_AAH_(PROBLEMA) + SU CLAVE PAPÁ! Su clave. 
# Como q hay q hacer esto automatizado no... or maybe not fully 100%
# Pero tipo... una db donde... sí hacemos la de (Código_de_Examen_Problema)
# Más su respuesta. 

# WHAT DO THEY MISS KNOWING?
# Esa es la pregunta central, how can we identify what they miss knowing?
# ChatGPT, DeepL, any good AI can teach them, but they need to know what they don't know.
# jaja! 😂 Funny but real.

# Luego... Asumiendo que completo todos los pdfs... 
# Entonces ya tengo una base de datos con todas las imágenes
# Y sus respuestas.
# We could try like identify where there are only words -> Actually pass it
# to words and save it better.

# Tendríamos todas las preguntas de nivel 3... de UNI, UNMSM, PUCP, etc.
# Y luego... todas son preguntas de nivel 3...
# FALTA SEGMENTAR POR TEMA.

# También preguntas de nivel 2, nivel 1, etc. pero... 
# De donde saco las preguntas de nivel 1 y 2? . . .
# We can find them online... I just... how do you know they are hard or easy
# enough for a level 1 or 2? 

# How about the things that you must definetly know for a level 1, 2 or 3?
# But these are questions once I complete having all level 3 questions.
# This project is able to extract any questions from any pdf, so... 
# it is just about time to find the questions.

# Once we have questions of level 1, 2 and 3, separted by topic,
# then we can start training... students. And rebuild upon that.
# AI Will do show students how they understand the problems, 
# we do not care about teaching but providing the best material
# for them to learn by themselves.

# We could connect with the other project of statistics.
# SUMMARIES OF FORMULAS/Things one must know. 



# Batch runner for treecare.visualize_one across full PDFs.
# - Shows progress: "page X of N completed".
# - After each file, asks whether to continue.
# - Uses the user's Python path and outputs to data/crops_quick by default.

PY="/usr/local/bin/python3.13"
OUT_DIR="data/crops_quick"

# You can edit this list to add/remove PDFs.
# Format: <pdf_filename>:<columns s|d>:<pages>
ITEMS=(
  "EX_Adm_UNI_2025_2_AAH.pdf:d:41"
  "EX_Adm_UNI_2025_2_MAT.pdf:s:43"
  "EX_Adm_UNI_2025_2_SCI.pdf:s:34"
)

format_columns() {
  if [[ "$1" == "d" ]]; then echo "double"; else echo "single"; fi
}

trap 'echo; echo "Interrupted. Exiting."; exit 130' INT

echo "Output directory: $OUT_DIR"
mkdir -p "$OUT_DIR"

for item in "${ITEMS[@]}"; do
  IFS=":" read -r PDF_FILE COL TOTAL_PAGES <<< "$item"
  TITLE="${PDF_FILE%.pdf}"

  echo "\n==== Processing $TITLE ===="
  echo "Columns: $(format_columns "$COL")  |  Pages: $TOTAL_PAGES"

  for ((p=1; p<=TOTAL_PAGES; p++)); do
    echo "-> $TITLE: page $p of $TOTAL_PAGES..."
    "$PY" -m treecare.visualize_one \
      --pdf "$PDF_FILE" \
      --page "$p" \
      --columns "$COL" \
      --out "$OUT_DIR"
    echo "   $TITLE: page $p of $TOTAL_PAGES completed."
  done

  # Prompt to continue after finishing this PDF
  echo
  read -r -p "Finished $TITLE. Continue to next? [Y/n]: " ans
  ans=${ans:-Y}
  case "$ans" in
    [Nn]*) echo "Stopping as requested."; exit 0;;
    *)     echo "Continuing...";;
  esac
done

echo "\nAll PDFs processed. ✅"
