import type { Metadata } from "next";
import "../styles.css";
import "./next-app.css";

export const metadata: Metadata = {
  title: "HR Knowledge",
  description: "HR policy assistant backed by verified company documents",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="vi">
      <body>{children}</body>
    </html>
  );
}
