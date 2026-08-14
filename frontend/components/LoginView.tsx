"use client";

import { FormEvent, useState } from "react";
import { BookOpen, LoaderCircle, LockKeyhole, ShieldCheck } from "lucide-react";
import { api, ApiClientError } from "@/lib/api";
import type { User } from "@/lib/types";

const DEPARTMENTS = [
  { value: "HR", label: "Nhân sự (HR)" },
  { value: "Engineering", label: "Kỹ thuật (Engineering)" },
  { value: "IT", label: "Công nghệ thông tin (IT)" },
  { value: "Finance", label: "Tài chính (Finance)" },
  { value: "Sales", label: "Kinh doanh (Sales)" },
  { value: "Marketing", label: "Marketing" },
  { value: "Operations", label: "Vận hành (Operations)" },
  { value: "Legal", label: "Pháp chế (Legal)" },
];

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
        setNotice("Tài khoản đã được Backend tạo thành công. Bạn có thể đăng nhập ngay.");
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
        <div className="brand-lockup"><BookOpen size={22} /><span>HR Intelligence</span></div>
        <div className="login-context-copy">
          <p className="eyebrow">ENTERPRISE DOCUMENT INTELLIGENCE</p>
          <h1>Hiểu chính sách HR. Tin cậy từng nguồn.</h1>
          <p>Nền tảng AI giúp nhân viên tra cứu tài liệu nội bộ với câu trả lời có trích dẫn và nguồn đối soát rõ ràng.</p>
          <div className="trust-points">
            <span><ShieldCheck size={20} /> Câu trả lời có nguồn kiểm chứng</span>
            <span><LockKeyhole size={20} /> Dữ liệu nội bộ được phân quyền</span>
          </div>
        </div>
      </section>
      <section className="login-form-panel">
        <form className="login-form" onSubmit={submit}>
          <div className="brand-lockup brand-lockup-dark"><BookOpen size={21} /><span>HR Intelligence</span></div>
          <div>
            <h2>{mode === "login" ? "Đăng nhập" : "Tạo tài khoản"}</h2>
            <p>{mode === "login" ? "Truy cập không gian tri thức nhân sự của doanh nghiệp." : "Tạo tài khoản để bắt đầu tra cứu tài liệu HR."}</p>
          </div>
          {mode === "register" && <label>Họ và tên<input value={fullName} onChange={(event) => setFullName(event.target.value)} required /></label>}
          {mode === "register" && <label>Phòng ban<select value={department} onChange={(event) => setDepartment(event.target.value)} required><option value="" disabled>Chọn phòng ban</option>{DEPARTMENTS.map((item) => <option value={item.value} key={item.value}>{item.label}</option>)}</select><small className="field-hint">Tài khoản đăng ký mới luôn có quyền Nhân viên. Quyền quản trị chỉ do quản trị viên cấp.</small></label>}
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
          <p className="form-note">Bằng việc tiếp tục, bạn xác nhận chỉ sử dụng dữ liệu theo quyền truy cập được cấp.</p>
        </form>
      </section>
    </main>
  );
}
