#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PYTHON="${ROOT_DIR}/.venv/bin/python"

if [[ ! -x "${VENV_PYTHON}" ]]; then
  echo "Error: expected virtual environment at .venv/bin/python" >&2
  exit 1
fi

WIKI_DIR="${ROOT_DIR}/obsidian_main/llm-wiki"
DOCS_DIR="${ROOT_DIR}/obsidian_main/docs"

cd "${ROOT_DIR}"

echo "Removing generated Obsidian output:"
echo "  ${WIKI_DIR}"
echo "  ${DOCS_DIR}"
rm -rf "${WIKI_DIR}" "${DOCS_DIR}"

mkdir -p "${WIKI_DIR}" "${DOCS_DIR}"

mapfile -t SOURCES < <(
  find "${ROOT_DIR}/archive" -maxdepth 1 -type f \
    \( -iname '*.pdf' -o -iname '*.docx' -o -iname '*.doc' -o -iname '*.md' -o -iname '*.txt' \) \
    -print | sort
)

if [[ "${#SOURCES[@]}" -eq 0 ]]; then
  echo "No archive sources found."
  exit 0
fi

for source in "${SOURCES[@]}"; do
  echo "Ingesting ${source}"
  llm-wiki ingest "${source}"
done

echo "Done."
