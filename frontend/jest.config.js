// frontend/jest.config.js
const nextJest = require("next/jest");

const createJestConfig = nextJest({
  dir: "./",
});

/** @type {import('jest').Config} */
const customJestConfig = {
  setupFilesAfterEnv: ["<rootDir>/jest.setup.js"],
  testEnvironment: "jest-environment-jsdom",
  testPathIgnorePatterns: ["<rootDir>/node_modules/", "<rootDir>/.next/"],
  collectCoverageFrom: [
    "lib/**/*.{ts,tsx}",
    "components/**/*.{ts,tsx}",
    "pages/**/*.{ts,tsx}",
    "!**/*.d.ts",
  ],
  coverageThreshold: {
    global: {
      branches: 80,
      functions: 80,
      lines: 80,
      statements: 80,
    },
  },
};

module.exports = async () => {
  const config = await createJestConfig(customJestConfig)();
  // next/jest prepends its own defaults (incl. a blanket "/node_modules/" rule)
  // to transformIgnorePatterns rather than replacing them. react-markdown and
  // its large remark/rehype/mdast/unist/etc. dependency tree ship as ESM-only
  // packages that need transforming, so replace the array entirely instead of
  // appending — transform everything except css-module files.
  config.transformIgnorePatterns = ["^.+\\.module\\.(css|sass|scss)$"];
  return config;
};
