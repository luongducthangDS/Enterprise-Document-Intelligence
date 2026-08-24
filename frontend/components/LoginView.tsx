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
        await api.register(email.trim(), password, fullName.trim());
        setMode("login");
        setNotice("Tài khoản đã được tạo. Bạn có thể đăng nhập ngay.");
      } else {
        await api.login(email.trim(), password);
        onAuthenticated(await api.me());
      }
    } catch (reason) {
      if (reason instanceof ApiClientError && reason.status === 401) setError("Email hoặc mật khẩu không đúng.");
      else if (reason instanceof ApiClientError && reason.status === 409) setError("Email này đã được đăng ký. Bạn có thể đăng nhập ngay.");
      else setError(reason instanceof ApiClientError ? reason.message : "Không thể xác thực tài khoản.");
    } finally {
      setLoading(false);
    }
  }

  function changeMode(nextMode: "login" | "register") {
    setMode(nextMode);
    setError("");
    setNotice("");
  }

  return (
    <main className="current-login-scene" data-ui="cusion-shell">
      <a className="skip-to-login" href="#login-form">Chuyển tới biểu mẫu đăng nhập</a>
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
          <div className="login-mode-switch" role="tablist" aria-label="Chọn hình thức xác thực">
            <button className={mode === "login" ? "active" : ""} role="tab" aria-selected={mode === "login"} type="button" onClick={() => changeMode("login")}>Đăng nhập</button>
            <button className={mode === "register" ? "active" : ""} role="tab" aria-selected={mode === "register"} type="button" onClick={() => changeMode("register")}>Đăng ký</button>
          </div>
          <form id="login-form" className="login-form current-login-form" onSubmit={submit}>
            <div>
              <p className="eyebrow">{mode === "login" ? "CHÀO MỪNG TRỞ LẠI" : "TẠO HỒ SƠ MỚI"}</p>
              <h2>{mode === "login" ? "Đăng nhập hệ thống" : "Tạo tài khoản"}</h2>
              <p>{mode === "login" ? "Tiếp tục tới kho tri thức nội bộ của bạn." : "Tài khoản mới được quản lý và bảo vệ theo phân quyền của hệ thống."}</p>
            </div>
            {mode === "register" && <label>Họ và tên<input autoComplete="name" value={fullName} onChange={(event) => setFullName(event.target.value)} required /></label>}
            <label>Email công việc<input autoComplete="email" type="email" value={email} onChange={(event) => setEmail(event.target.value)} required /></label>
            <label>Mật khẩu<input autoComplete={mode === "login" ? "current-password" : "new-password"} type="password" minLength={8} value={password} onChange={(event) => setPassword(event.target.value)} required aria-describedby="password-rule" /></label>
            {mode === "register" && <p className="form-note" id="password-rule">Mật khẩu tối thiểu 8 ký tự.</p>}
            {error && <div className="inline-error animate__animated animate__shakeX motion-fast" role="alert">{error}</div>}
            {notice && <div className="inline-success animate__animated animate__fadeIn motion-fast" role="status">{notice}</div>}
            <button className="primary-command current-login-submit" disabled={loading} type="submit" data-ui="primary-action">
              {loading ? <LoaderCircle className="spin" size={17} /> : <LockKeyhole size={17} />}
              {loading ? "Đang xử lý" : mode === "login" ? "Đăng nhập" : "Đăng ký"}
            </button>
            <p className="form-note">{mode === "login" ? "Dùng email công ty đã đăng ký để truy cập kho tri thức nội bộ." : "Tài khoản mới mặc định là Nhân viên. Phòng ban và quyền quản lý cần được Quản trị hệ thống xác nhận."}</p>
          </form>
        </section>
      </section>
    </main>
  );
}
