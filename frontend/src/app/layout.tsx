import type { Metadata } from "next";
import "./globals.css";
import { Navbar } from "@/components/Navbar";
import { Footer } from "@/components/Footer";
import { DemoBanner } from "@/components/DemoBanner";

export const metadata: Metadata = {
  title: "PSE Pulse — Personal Azure Edition",
  description:
    "Lightweight personal Philippine Stock Exchange analytics and forecasting shell optimized for Azure for Students.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="antialiased min-h-screen flex flex-col justify-between selection:bg-blue-500 selection:text-white">
        <div>
          <DemoBanner />
          <Navbar />
          <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
            {children}
          </main>
        </div>
        <Footer />
      </body>
    </html>
  );
}
