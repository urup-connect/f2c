import type { Metadata } from "next";
import { DM_Sans, Playfair_Display } from "next/font/google";
import "./globals.css";
import { SITE_CONFIG } from "@/lib/site";

/*
 * Brand typefaces. See design/features/brand-design-system.md section 6.2.
 * next/font downloads and self-hosts these at build time, so member browsers never contact
 * Google's font hosts.
 */
const dmSans = DM_Sans({
  variable: "--font-dm-sans",
  subsets: ["latin"],
});

// The guidelines show a "Light" cut, but Playfair Display starts at 400 on Google Fonts.
// See design/features/brand-design-system.md risk 2.
const playfairDisplay = Playfair_Display({
  variable: "--font-playfair-display",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
});

export const metadata: Metadata = {
  /*
   * Absolute origin for canonical and social URLs, so they never resolve against whichever
   * host served the request.
   */
  metadataBase: new URL(SITE_CONFIG.siteUrl),
  /*
   * Default deny. Only the landing page overrides this, so a route added later is kept out of
   * search results without anyone having to remember to exclude it.
   * See design/features/public-landing-and-auth-routing.md section 6.3.
   */
  robots: { index: false, follow: false },
  title: {
    default: "Cultivators Collective",
    template: "%s | Cultivators Collective",
  },
  description:
    "A cannabis club for members, by cultivators. Connecting members with trusted cultivators through a premium club experience built on quality, transparency and community.",
  applicationName: "Cultivators Collective",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en-ZA"
      className={`${dmSans.variable} ${playfairDisplay.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
