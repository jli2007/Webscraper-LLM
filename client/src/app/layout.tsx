import type { Metadata } from "next";
import "./globals.css";


export const metadata: Metadata = {
  title: "challenge",
  description: "orchid challenge james li",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
            <link rel="icon" href="/logo.png" />
      <body
        className={`antialiased`}
      >
        {children}
      </body>
    </html>
  );
}
