import type { Metadata } from "next";
import { IBM_Plex_Sans } from "next/font/google";
import { AppChrome } from "@/components/AppChrome";
import "./globals.css";

const ibm = IBM_Plex_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-ibm",
});

export const metadata: Metadata = {
  title: "Photos retrieval discovery snapshot",
  description: "Frozen dashboard, RAG search, and methodology for Google Photos retrieval feedback.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={ibm.variable}>
      <body className={ibm.className}>
        <AppChrome>{children}</AppChrome>
      </body>
    </html>
  );
}
