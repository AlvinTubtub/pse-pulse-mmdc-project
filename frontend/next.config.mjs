/** @type {import('next').NextConfig} */
const nextConfig = {
  // Required for Azure VM static serving via Nginx without Node runtime
  output: 'export',
  images: {
    unoptimized: true,
  },
};

export default nextConfig;
