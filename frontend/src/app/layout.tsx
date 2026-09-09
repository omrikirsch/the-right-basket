import type { Metadata } from "next";
import { Heebo } from "next/font/google";
import "./globals.css";

const heebo = Heebo({
  variable: "--font-heebo",
  subsets: ["hebrew", "latin"],
});

export const metadata: Metadata = {
  title: "העגלה הנכונה | השוואת מחירי סופרמרקט",
  description:
    "השוואת מחירי מוצרים בין רשתות השיווק בישראל, על בסיס קבצי המחירים " +
    "שהרשתות מחויבות לפרסם. בונים סל וירטואלי ומגלים באיזו רשת הוא הזול ביותר.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="he" dir="rtl" className={`${heebo.variable} h-full antialiased`}>
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
