"use client";

import { useEffect } from "react";

/**
 * WarmupPing: Component vô hình, mount một lần duy nhất ở RootLayout.
 *
 * Đánh thức SONG SONG cả Backend và Agent ngay khi người dùng mở trang web —
 * cả hai service trên Render nhận tín hiệu cùng một lúc nên thức dậy đồng thời,
 * giảm thời gian chờ xuống còn 25–30s thay vì 60s nếu làm tuần tự.
 *
 * Sử dụng keepalive: true để đảm bảo request được gửi đi ngay cả khi
 * người dùng chuyển trang trước khi fetch hoàn tất.
 */
function getHealthUrl(rawUrl: string | undefined): string | null {
  if (!rawUrl) return null;
  const cleaned = rawUrl.trim().replace(/\/api\/v1.*$/, "").replace(/\/+$/, "");
  return cleaned ? `${cleaned}/health` : null;
}

export default function WarmupPing() {
  useEffect(() => {
    const targets: string[] = [];

    const backendHealth = getHealthUrl(process.env.NEXT_PUBLIC_API_BASE_URL);
    if (backendHealth) targets.push(backendHealth);

    const agentHealth = getHealthUrl(process.env.NEXT_PUBLIC_AGENT_BASE_URL);
    if (agentHealth) targets.push(agentHealth);

    if (targets.length === 0) {
      console.warn("[WarmupPing] Không tìm thấy URL của Backend hoặc Agent để đánh thức.");
      return;
    }

    console.info("[WarmupPing] 🚀 Đang gửi tín hiệu đánh thức song song tới:", targets);

    Promise.all(
      targets.map((url) =>
        fetch(url, { method: "GET", keepalive: true, mode: "cors" })
          .then((res) => {
            console.info(`[WarmupPing] ✅ Đã đánh thức thành công: ${url} (HTTP ${res.status})`);
          })
          .catch((err) => {
            console.warn(`[WarmupPing] ⚠️ Không thể kết nối trực tiếp tới ${url}:`, err);
          })
      )
    );
  }, []);

  return null;
}
