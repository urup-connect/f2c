import type { Metadata } from "next";
import { DM_Sans, Playfair_Display } from "next/font/google";
import "./globals.css";
import { API_BASE_META_NAME, publicApiBaseUrl } from "@/lib/api-address";
import { siteConfig } from "@/lib/site";

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

/**
 * Site metadata, built per request.
 *
 * A function rather than `export const metadata`, because that object is evaluated when this
 * module is first imported — and `next build` imports it to analyse the route tree. `metadataBase`
 * reads `SITE_URL`, so reading it on import would bake the origin into the image and undo
 * design/deploy.md R-D4. `generateMetadata` runs during render, where the container's environment
 * is the one that answers.
 */
export function generateMetadata(): Metadata {
  return {
    /*
     * Absolute origin for canonical and social URLs, so they never resolve against whichever
     * host served the request.
     */
    metadataBase: new URL(siteConfig().siteUrl),
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
}

/**
 * Rendered per request, never prerendered.
 *
 * The `<meta>` tag below carries `DJANGO_API_PUBLIC_URL`, and a statically prerendered page would
 * bake whatever that variable said at **build** time into its HTML — which is the build-time
 * coupling this whole arrangement exists to remove (`design/todo.md` Block 0 P6). The cost is
 * small and was measured: every route that matters here was already dynamic before this line,
 * because every page reads cookies. What becomes dynamic is `/_not-found`, `/signup/paid` and
 * `/signup/cancelled`.
 */
export const dynamic = 'force-dynamic'

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en-ZA"
      className={`${dmSans.variable} ${playfairDisplay.variable} h-full antialiased`}
    >
      <head>
        {/*
         * The API address the browser uses, handed over at request time. React hoists this into
         * <head>; `lib/api.ts` reads it there. See `lib/api-address.ts` for why it is not a
         * NEXT_PUBLIC_ variable.
         */}
        <meta name={API_BASE_META_NAME} content={publicApiBaseUrl()} />
      </head>
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
