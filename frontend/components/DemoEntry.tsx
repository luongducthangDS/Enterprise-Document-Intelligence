"use client";

import { useState } from "react";
import { BookOpen, Calculator, LoaderCircle, LockKeyhole, Package, ShieldCheck, Users } from "lucide-react";
import { api, ApiClientError } from "@/lib/api";
import type { User } from "@/lib/types";

const ROLES = [
  { department: "HR", label: "Nhân viên Nhân sự", detail: "Nghỉ phép, làm thêm giờ, phúc lợi", icon: Users },
  { department: "PRODUCT", label: "Nhân viên Sản phẩm", detail: "PRD, roadmap, báo cáo thử nghiệm", icon: Package },
  { department: "ACCOUNTING", label: "Nhân viên Kế toán", detail: "Hạn mức chi, quy chế tài chính", icon: Calculator },
] as const;

// Render free ngủ khi không có truy cập: một lần thức có thể vượt timeout 45s của request.
const MAX_ATTEMPTS = 3;

export function DemoEntry({ onAuthenticated }: { onAuthenticated: (user: User) => void }) {
  const [pending, setPending] = useState("");
  const [waking, setWaking] = useState(false);
  const [error, setError] = useState("");

  async function enter(department: string) {
    setPending(department);
    setError("");
    setWaking(false);
    for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt += 1) {
      try {
        await api.demoSession(department);
        onAuthenticated(await api.me());
        return;
      } catch (reason) {
        const unreachable = !(reason instanceof ApiClientError) || reason.status === 0;
        if (unreachable && attempt < MAX_ATTEMPTS) {
          setWaking(true);
          continue;
        }
        setError(unreachable ? "Máy chủ chưa phản hồi. Vui lòng thử lại sau ít phút." : (reason as ApiClientError).message);
        break;
      }
    }
    setPending("");
    setWaking(false);
  }

  return (
    <main className="current-login-scene" data-ui="cusion-shell">
      <div className="login-ambient login-ambient-primary" aria-hidden="true" />
      <div className="login-ambient login-ambient-gold" aria-hidden="true" />
      <section className="current-login-layout">
        <article className="current-login-hero" data-ui="hero">
          <div className="current-login-brand"><span className="brand-mark"><BookOpen size={20} /></span><span><strong>Tri thức nội bộ</strong><small>Trợ lý AI</small></span></div>
          <div className="current-login-copy">
            <p className="eyebrow">TRỢ LÝ AI TRI THỨC NỘI BỘ</p>
            <h1>Tri thức nội bộ,<br />sẵn sàng khi bạn cần.</h1>
            <p>Tra cứu quy trình, quy định và chính sách nội bộ, nhận câu trả lời rõ ràng và kiểm chứng từng nguồn đối soát.</p>
          </div>
          <div className="current-login-trust">
            <span><ShieldCheck size={18} /><span><strong>Trả lời có trích dẫn</strong><small>Kèm nguồn tài liệu để đối soát</small></span></span>
            <span><LockKeyhole size={18} /><span><strong>Truy cập có phân quyền</strong><small>Theo vai trò và phòng ban</small></span></span>
          </div>
        </article>

        <section className="current-login-card" data-ui="membership-card">
          <div className="login-form current-login-form">
            <div>
              <p className="eyebrow">BẢN DEMO · KHÔNG CẦN ĐĂNG NHẬP</p>
              <h2>Chọn vai trò để bắt đầu</h2>
              <p>Mỗi vai trò chỉ thấy tài liệu được phép. Dữ liệu trong bản demo là dữ liệu mô phỏng.</p>
            </div>
            <div className="demo-role-list">
              {ROLES.map(({ department, label, detail, icon: Icon }) => (
                <button className="demo-role" disabled={Boolean(pending)} key={department} onClick={() => void enter(department)} type="button">
                  {pending === department ? <LoaderCircle className="spin" size={20} /> : <Icon size={20} />}
                  <span><strong>{label}</strong><small>{detail}</small></span>
                </button>
              ))}
            </div>
            {waking && <p className="form-note" role="status">Máy chủ miễn phí đang khởi động, có thể mất khoảng 1 phút...</p>}
            {error && <div className="inline-error" role="alert">{error}</div>}
          </div>
        </section>
      </section>
    </main>
  );
}
