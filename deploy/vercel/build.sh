#!/usr/bin/env bash
# Assembles the Vercel upload in .vercel-deploy/ (git-ignored):
#   public/   the Expo web export, served as static files
#   api/      the Python function that wraps backend/server.py
#   backend/  the backend modules, bundled into the function only
# Then: cd .vercel-deploy && npx vercel deploy --prod
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
OUT="$ROOT/.vercel-deploy"
rm -rf "$OUT/public" "$OUT/api" "$OUT/backend"
mkdir -p "$OUT/backend"

# Empty backend URL = same origin as the page. Set here so frontend/.env's
# localhost value can't leak into the build.
(cd "$ROOT/frontend" && EXPO_PUBLIC_BACKEND_URL="" npx expo export --platform web --output-dir "$OUT/public" --clear)
if grep -rq "localhost:80" "$OUT/public/_expo"; then
  echo "Build still points at a localhost backend; aborting." >&2
  exit 1
fi

# The Vercel CLI never uploads node_modules/ folders, but Expo exports the
# icon fonts and library images to public/assets/node_modules/. Rename the
# folder and point the bundle at the new path.
if [ -d "$OUT/public/assets/node_modules" ]; then
  mv "$OUT/public/assets/node_modules" "$OUT/public/assets/vendor"
  find "$OUT/public/_expo" -name "*.js" -exec sed -i '' 's#/assets/node_modules/#/assets/vendor/#g' {} +
fi

cp -R "$ROOT/deploy/vercel/api" "$OUT/api"
cp "$ROOT/deploy/vercel/vercel.json" "$ROOT/deploy/vercel/requirements.txt" "$OUT/"
cp "$ROOT"/backend/*.py "$ROOT/backend/research_admin.html" "$OUT/backend/"
# Game scenarios and the Coach knowledge base are read at runtime.
cp -R "$ROOT/backend/content" "$OUT/backend/"
rm -f "$OUT/backend/manage_researchers.py"
echo "Built $OUT"
