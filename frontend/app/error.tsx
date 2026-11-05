"use client";

export default function ErrorPage({ reset }: { error: Error; reset: () => void }) {
  return (
    <div className="app-loading" role="alert">
      <p>Đã xảy ra lỗi khi hiển thị trang.</p>
      <button className="primary-command" onClick={reset} type="button">Thử lại</button>
    </div>
  );
}
