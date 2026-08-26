import type { NextConfig } from "next";

const isStaticExport = process.env.NEXT_OUTPUT_MODE !== "server";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  ...(isStaticExport && { output: "export" as const }),
  images: {
    unoptimized: true, // Tránh lỗi khi dùng thẻ <Image /> của Next.js
  },
  ...(process.env.NEXT_DIST_DIR && { distDir: process.env.NEXT_DIST_DIR }),
};

export default nextConfig;