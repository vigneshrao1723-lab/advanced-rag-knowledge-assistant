import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Produces a minimal, self-contained server bundle for the Docker image
  // (infra/docker/frontend.Dockerfile) instead of shipping full node_modules.
  output: "standalone",
};

export default nextConfig;
