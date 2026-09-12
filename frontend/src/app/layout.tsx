import type { Metadata } from "next";
import { Geist, Geist_Mono, Newsreader, Source_Serif_4 } from "next/font/google";
import { Providers } from "@/components/providers";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

const newsreader = Newsreader({
  variable: "--font-serif",
  subsets: ["latin"],
  style: ["normal", "italic"],
});

const sourceSerif = Source_Serif_4({
  variable: "--font-source-serif",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Storykeep",
  description: "A personal RSS reader and lifelong article archive.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} ${newsreader.variable} ${sourceSerif.variable} h-dvh overflow-hidden antialiased`}
      suppressHydrationWarning
    >
      <body className="flex h-dvh min-h-0 flex-col overflow-hidden">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
