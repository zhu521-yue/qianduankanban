import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AI客户看板",
  description: "由后端与 weidian 数据库驱动的销售及客户经营看板",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="zh-CN"><body>{children}</body></html>;
}
