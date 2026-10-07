import type { Metadata, Viewport } from "next";
import { Hind_Siliguri, Plus_Jakarta_Sans } from "next/font/google";
import "./globals.css";
import { Providers } from "./providers";
import { THEME_INIT_SCRIPT } from "@/lib/theme";

// Brand type: Plus Jakarta Sans (Latin) + Hind Siliguri (Bangla).
const jakarta = Plus_Jakarta_Sans({ variable: "--font-jakarta", subsets: ["latin"], weight: ["400", "500", "600", "700", "800"] });
const bengali = Hind_Siliguri({ variable: "--font-bn", subsets: ["bengali", "latin"], weight: ["400", "500", "600", "700"] });

export const metadata: Metadata = {
  title: "AgentEr Upay",
  description: "Liquidity forecasting for upay agents. Prototype for the DIU CPC x upay AI Hackathon 2026.",
};
export const viewport: Viewport = {
  width: "device-width", initialScale: 1,
  themeColor: [{ media: "(prefers-color-scheme: light)", color: "#1A4FD6" }, { media: "(prefers-color-scheme: dark)", color: "#070F26" }],
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" suppressHydrationWarning className={`${jakarta.variable} ${bengali.variable} h-full antialiased`}>
      <head><script dangerouslySetInnerHTML={{ __html: THEME_INIT_SCRIPT }} /></head>
      <body className="min-h-full">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
