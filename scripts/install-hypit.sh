#!/bin/sh
set -eu
repo_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
command -v npm >/dev/null || { echo '请先安装 Node.js 22.15+ 和 npm'; exit 1; }
node -e 'const [major,minor]=process.versions.node.split(".").map(Number);if(major<22||(major===22&&minor<15))process.exit(1)' || { echo '需要 Node.js 22.15+'; exit 1; }
npm install --prefix "$repo_dir/.hypit-runtime" --save-exact --registry https://registry.npmjs.org @hypit/hypit@0.3.1
"$repo_dir/.hypit-runtime/node_modules/.bin/hypit" version
