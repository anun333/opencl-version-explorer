#!/bin/sh
# Download the two Khronos repositories (about 11 MB) into sources/ as bare clones.
#   ./fetch.sh            pin to the commits in PIN (reproducible)
#   ./fetch.sh --latest   follow upstream main
set -e
cd "$(dirname "$0")"
. ./PIN
mkdir -p sources
[ -d sources/OpenCL-Docs.git ]    || git clone --bare https://github.com/KhronosGroup/OpenCL-Docs.git    sources/OpenCL-Docs.git
[ -d sources/OpenCL-Headers.git ] || git clone --bare https://github.com/KhronosGroup/OpenCL-Headers.git sources/OpenCL-Headers.git
if [ "$1" = "--latest" ]; then
  git --git-dir=sources/OpenCL-Docs.git    fetch --tags origin '+refs/heads/*:refs/heads/*'
  git --git-dir=sources/OpenCL-Headers.git fetch --tags origin '+refs/heads/*:refs/heads/*'
  echo "following upstream main (results will differ from the pinned ones)"
else
  git --git-dir=sources/OpenCL-Docs.git    cat-file -e "$DOCS_COMMIT"    || { echo "pinned docs commit not in clone; try --latest"; exit 1; }
  git --git-dir=sources/OpenCL-Headers.git cat-file -e "$HEADERS_COMMIT" || { echo "pinned headers commit not in clone; try --latest"; exit 1; }
  git --git-dir=sources/OpenCL-Docs.git    update-ref refs/heads/main "$DOCS_COMMIT"
  git --git-dir=sources/OpenCL-Headers.git update-ref refs/heads/main "$HEADERS_COMMIT"
  echo "pinned: docs $DOCS_COMMIT"; echo "        headers $HEADERS_COMMIT"
fi
