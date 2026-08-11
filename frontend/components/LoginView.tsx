"use client";

import { FormEvent, useState } from "react";
import { BookOpen, LoaderCircle, LockKeyhole, ShieldCheck } from "lucide-react";
import { api, ApiClientError } from "@/lib/api";
import type { User } from "@/lib/types";

export function LoginView({ onAuthenticated }: { onAuthenticated: (user: User) => void }) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [department, setDepartment] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError("");
    setNotice("");
    try {
      if (mode === "register") {
        await api.register(email.trim(), password, fullName.trim(), department.trim());
        setMode("login");
        setNotice("Tài khoản Supabase đã được tạo. Hãy xác nhận email nếu project yêu cầu, rồi đăng nhập.");
      } else {
        await api.login(email.trim(), password);
        onAuthenticated(await api.me());
      }
    } catch (reason) {
      setError(reason instanceof ApiClientError ? reason.message : "Không thể xác thực tài khoản.");
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
            <h2>{mode === "login" ? "Đăng nhập" : "Tạo tài khoản"}</h2>
            <p>{mode === "login" ? "Sử dụng tài khoản Supabase của hệ thống." : "Tài khoản mới được tạo qua Supabase Auth."}</p>
          </div>
          {mode === "register" && <label>Họ và tên<input value={fullName} onChange={(event) => setFullName(event.target.value)} required /></label>}
          {mode === "register" && <label>Phòng ban<input value={department} onChange={(event) => setDepartment(event.target.value)} required /></label>}
          <label>Email công việc<input type="email" value={email} onChange={(event) => setEmail(event.target.value)} required /></label>
          <label>Mật khẩu<input type="password" minLength={6} value={password} onChange={(event) => setPassword(event.target.value)} required /></label>
          {error && <div className="inline-error" role="alert">{error}</div>}
          {notice && <div className="inline-success" role="status">{notice}</div>}
          <button className="primary-command" disabled={loading} type="submit">
            {loading ? <LoaderCircle className="spin" size={17} /> : <LockKeyhole size={17} />}
            {loading ? "Đang xử lý" : mode === "login" ? "Đăng nhập" : "Đăng ký"}
          </button>
          <button
            className="secondary-command auth-mode-command"
            type="button"
            onClick={() => { setMode(mode === "login" ? "register" : "login"); setError(""); setNotice(""); }}
          >
            {mode === "login" ? "Chưa có tài khoản? Đăng ký" : "Đã có tài khoản? Đăng nhập"}
          </button>
          <p className="form-note">Tài khoản và phiên đăng nhập được quản lý bởi Supabase Auth.</p>
        </form>
      </section>
    </main>
  );
}
