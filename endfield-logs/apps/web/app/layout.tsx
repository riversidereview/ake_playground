import type { Metadata } from "next";
import type { ReactNode } from "react";

import "./globals.css";
import { AppShell } from "../components/app-shell";
import { I18nProvider } from "../lib/i18n/context";

export const metadata: Metadata = {
  title: "Endfield Battle Logs | 终末地战斗日志",
  description: "Arknights: Endfield combat log analytics, speedrun leaderboards, and full battle reports.",
  icons: {
    icon: [
      { url: "/site-favicon-20260502.ico" },
      { url: "/site-logo-20260502.png", type: "image/png", sizes: "1024x1024" },
    ],
    shortcut: "/site-favicon-20260502.ico",
    apple: "/site-logo-20260502.png",
  },
};

type RootLayoutProps = {
  children: ReactNode;
};

export default function RootLayout({ children }: RootLayoutProps) {
  return (
    <html lang="en">
      <body>
        <I18nProvider>
          <AppShell>{children}</AppShell>
        </I18nProvider>
      </body>
    </html>
  );
}
