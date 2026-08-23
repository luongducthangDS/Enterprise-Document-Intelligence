import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  output: "export", // Bắt buộc để xuất trang tĩnh cho Cloudflare Pages
  images: {
    unoptimized: true, // Tránh lỗi khi dùng thẻ <Image /> của Next.js
  },
  ...(process.env.NEXT_DIST_DIR && { distDir: process.env.NEXT_DIST_DIR }),
};

export default nextConfig;