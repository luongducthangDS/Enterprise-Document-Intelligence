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
export default function WarmupPing() {
  useEffect(() => {
    const targets: string[] = [];

    // Target 1: Backend
    const backendUrl = process.env.NEXT_PUBLIC_API_BASE_URL;
    if (backendUrl) {
      targets.push(backendUrl.replace(/\/api\/v1.*$/, "") + "/health");
    }

    // Target 2: AI Agent Service (tùy chọn — thêm NEXT_PUBLIC_AGENT_BASE_URL khi build)
    const agentUrl = process.env.NEXT_PUBLIC_AGENT_BASE_URL;
    if (agentUrl) {
      targets.push(agentUrl.replace(/\/api\/v1.*$/, "") + "/health");
    }

    if (targets.length === 0) return;

    // Bắn song song tất cả target cùng một lúc — fire-and-forget, không block UI
    Promise.all(
      targets.map((url) =>
        fetch(url, { method: "GET", keepalive: true }).catch(() => {
          /* Bỏ qua lỗi — chỉ cần gửi tín hiệu đánh thức */
        })
      )
    );
  }, []); // Chỉ chạy 1 lần khi mount

  return null; // Không render bất cứ thứ gì ra DOM
}
