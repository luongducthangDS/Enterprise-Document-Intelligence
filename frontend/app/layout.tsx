import type { Metadata } from "next";
import { Be_Vietnam_Pro, Playfair_Display } from "next/font/google";
import "animate.css";
import "../styles.css";
import "./next-app.css";
import WarmupPing from "../components/WarmupPing";

// Be Vietnam Pro: sans được thiết kế riêng cho tiếng Việt (đủ dấu, đủ weight).
// Playfair Display: serif display có subset vietnamese, thay "Instrument Serif"
// (không hỗ trợ tiếng Việt) cho các tiêu đề.
const sansFont = Be_Vietnam_Pro({
  subsets: ["latin", "vietnamese"],
  weight: ["400", "500", "600", "700", "800"],
  variable: "--font-sans",
  display: "swap",
});

const serifFont = Playfair_Display({
  subsets: ["latin", "vietnamese"],
  variable: "--font-serif",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Tri thức nội bộ",
  description: "Trợ lý AI tra cứu tài liệu và tri thức nội bộ, câu trả lời kèm nguồn đối soát",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="vi" className={`${sansFont.variable} ${serifFont.variable}`}>
      <body>
        {/* Đánh thức BE và Agent ngay khi trang mở — không ảnh hưởng UI */}
        <WarmupPing />
        {children}
      </body>
    </html>
  );
}
