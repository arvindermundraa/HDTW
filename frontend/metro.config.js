// metro.config.js
const { getDefaultConfig } = require("expo/metro-config");
const path = require('path');
const { FileStore } = require('metro-cache');

const config = getDefaultConfig(__dirname);

// Allow importing the repo-root design_guidelines.json (single source of
// truth for design tokens — see src/theme.ts's header comment) into
// frontend/src/theme.ts. Metro only resolves/watches files inside its
// project root by default, and a symlink + `unstable_enableSymlinks` was
// tried first but Metro still rejected it (the resolved realpath has to
// live inside a watched root regardless of the symlink flag) — so this
// explicitly adds the monorepo root as a second watched folder instead.
// `resolver.blockList` then excludes the large/unrelated directories next
// to it (backend/venv alone is ~340MB) so Metro's watcher never has to
// crawl them.
const workspaceRoot = path.resolve(__dirname, '..');
config.watchFolders = [workspaceRoot];
config.resolver.blockList = [
  /\/backend\/.*/,
  /\/\.git\/.*/,
  /\/docs\/.*/,
  /\/memory\/.*/,
  /\/test_reports\/.*/,
  /\/tests\/.*/,
  /\/\.claude\/.*/,
];

// Use a stable on-disk store (shared across web/android)
const root = process.env.METRO_CACHE_ROOT || path.join(__dirname, '.metro-cache');
config.cacheStores = [
  new FileStore({ root: path.join(root, 'cache') }),
];


// // Exclude unnecessary directories from file watching
// config.watchFolders = [__dirname];
// config.resolver.blacklistRE = /(.*)\/(__tests__|android|ios|build|dist|.git|node_modules\/.*\/android|node_modules\/.*\/ios|node_modules\/.*\/windows|node_modules\/.*\/macos)(\/.*)?$/;

// // Alternative: use a more aggressive exclusion pattern
// config.resolver.blacklistRE = /node_modules\/.*\/(android|ios|windows|macos|__tests__|\.git|.*\.android\.js|.*\.ios\.js)$/;

// Reduce the number of workers to decrease resource usage
config.maxWorkers = 2;

module.exports = config;
