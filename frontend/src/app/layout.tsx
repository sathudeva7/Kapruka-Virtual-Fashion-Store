import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Kapruka — Walk-in Store",
  description: "Walk the Kapruka fashion store and shop by talking to the assistant.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="h-full">
      <body className="h-full">{children}</body>
    </html>
  );
}
