"use client";

import { useEffect } from "react";

/**
 * WarmupPing: Component vô hình, mount một lần duy nhất ở RootLayout.
 *
 * Đánh thức Backend ngay khi người dùng mở trang, rồi nhờ Backend đánh thức Agent
 * (/warmup) — Agent không mở CORS cho trình duyệt nên không gọi trực tiếp được.
 *
 * Sử dụng keepalive: true để đảm bảo request được gửi đi ngay cả khi người
 * dùng chuyển trang trước khi fetch hoàn tất.
 */
function getServiceBase(rawUrl: string | undefined): string | null {
  if (!rawUrl) return null;
  const cleaned = rawUrl.trim().replace(/\/api\/v1.*$/, "").replace(/\/+$/, "");
  return cleaned || null;
}

export default function WarmupPing() {
  useEffect(() => {
    const base = getServiceBase(process.env.NEXT_PUBLIC_API_BASE_URL);
    if (!base) {
      console.warn("[WarmupPing] Không tìm thấy URL của Backend để đánh thức.");
      return;
    }

    const targets = [`${base}/health`, `${base}/warmup`];
    console.info("[WarmupPing] 🚀 Đang gửi tín hiệu đánh thức tới:", targets);

    Promise.all(
      targets.map((url) =>
        fetch(url, { method: "GET", keepalive: true, mode: "cors" })
          .then((res) => {
            console.info(`[WarmupPing] ✅ Đã đánh thức: ${url} (HTTP ${res.status})`);
          })
          .catch((err) => {
            console.warn(`[WarmupPing] ⚠️ Không thể kết nối trực tiếp tới ${url}:`, err);
          })
      )
    );
  }, []);

  return null;
}
