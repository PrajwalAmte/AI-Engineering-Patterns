import type { NextConfig } from "next";

// Set NEXT_PUBLIC_BASE_PATH=/AI-Engineering-Patterns in CI for GitHub Pages.
// Leave unset for local development so localhost:3000/ works as root.
const basePath = process.env.NEXT_PUBLIC_BASE_PATH ?? "";

const nextConfig: NextConfig = {
  output: "export",
  basePath,
  trailingSlash: true,
};

export default nextConfig;
