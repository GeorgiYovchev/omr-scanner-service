#!/usr/bin/env bash
# Sets up the REA/Ghidra toolchain env (all userspace, no sudo) and runs rea.
# Usage: ./run-rea.sh <rea-args...>
#   e.g. ./run-rea.sh doctor
#        ./run-rea.sh decompile /mnt/c/Repos/gitlab/OMR/lib64/LScannerSDK.dll \
#                     --procedure=SGetTicketInfo --snapshot ~/tools/omr-LScannerSDK.snapshot --format md
set -euo pipefail
export NVM_DIR="$HOME/.nvm"; . "$NVM_DIR/nvm.sh"; nvm use 22 >/dev/null
export JAVA_HOME="$HOME/tools/jdk21"
export PATH="$JAVA_HOME/bin:$PATH"
export GHIDRA_INSTALL_DIR="$HOME/tools/ghidra"
REA_DIR="/mnt/c/Repos/gitlab/OMR/rea"
exec node "$REA_DIR/scripts/rea.mjs" "$@"
