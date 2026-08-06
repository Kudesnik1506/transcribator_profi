import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Lean production image (web/Dockerfile.prod) — bundles only the
  // traced dependencies instead of the full node_modules tree.
  output: "standalone",
};

export default nextConfig;
