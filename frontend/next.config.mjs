import path from "node:path";

/** @type {import('next').NextConfig} */
const nextConfig = {
  // Required for Azure VM static serving via Nginx without Node runtime
  output: 'export',
  images: {
    unoptimized: true,
  },
  webpack(config) {
    if (process.env.NEXT_PUBLIC_DEMO_MODE === "false") {
      config.resolve.alias = {
        ...config.resolve.alias,
        "./demoFallbacks$": path.resolve(process.cwd(), "src/lib/productionFallbacks.ts"),
      };
    }
    return config;
  },
};

export default nextConfig;
