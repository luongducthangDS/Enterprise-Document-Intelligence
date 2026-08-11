"use client";

import { FormEvent, useState } from "react";
import { BookOpen, LoaderCircle, LockKeyhole, ShieldCheck } from "lucide-react";
import { api, ApiClientError } from "@/lib/api";
import type { User } from "@/lib/types";

export function LoginView({ onAuthenticated }: { onAuthenticated: (user: User) => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      await api.login(email.trim(), password);
      onAuthenticated(await api.me());
    } catch (reason) {
      setError(reason instanceof ApiClientError ? reason.message : "Không thể đăng nhập.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="login-shell">
      <section className="login-context">
        <div className="brand-lockup"><BookOpen size={22} /><span>HR Knowledge</span></div>
        <div className="login-context-copy">
          <p className="eyebrow">TRỢ LÝ AI HR DỰA TRÊN BẰNG CHỨNG</p>
          <h1>Nơi tin cậy để tra cứu chính sách nhân sự.</h1>
          <p>Câu trả lời được kiểm chứng từ kho tài liệu nội bộ và luôn đi kèm nguồn đối soát.</p>
          <div className="trust-points">
            <span><ShieldCheck size={20} /> Nguồn chính sách đã phê duyệt</span>
            <span><LockKeyhole size={20} /> Phân quyền do Backend kiểm soát</span>
          </div>
        </div>
      </section>
      <section className="login-form-panel">
        <form className="login-form" onSubmit={submit}>
          <div className="brand-lockup brand-lockup-dark"><BookOpen size={21} /><span>HR Knowledge</span></div>
          <div>
            <h2>Đăng nhập</h2>
            <p>Sử dụng tài khoản đã được cấp trong hệ thống.</p>
          </div>
          <label>Email công việc<input type="email" value={email} onChange={(event) => setEmail(event.target.value)} required /></label>
          <label>Mật khẩu<input type="password" value={password} onChange={(event) => setPassword(event.target.value)} required /></label>
          {error && <div className="inline-error" role="alert">{error}</div>}
          <button className="primary-command" disabled={loading} type="submit">
            {loading ? <LoaderCircle className="spin" size={17} /> : <LockKeyhole size={17} />}
            {loading ? "Đang xác thực" : "Đăng nhập"}
          </button>
          <p className="form-note">2FA và SSO đang được giữ ngoài scope cho tới khi Backend có contract chính thức.</p>
        </form>
      </section>
    </main>
  );
}
