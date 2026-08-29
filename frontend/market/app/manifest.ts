import type { MetadataRoute } from 'next'
import { STORE_BRAND } from '@/lib/brand'

/**
 * The web app manifest, for a browser that offers to install the store or that tints its own
 * chrome to match it.
 *
 * The colours are the two the logo leads with, in the roles the screens already give them:
 * `background_color` is the page ground the splash screen has to match, and `theme_color` is the
 * green of `StoreHeader` and the landing hero, so mobile browser chrome continues the header
 * rather than cutting a cream stripe above it. Both are literals rather than reads of
 * `app/globals.css`, because a manifest is JSON served to a browser and cannot resolve a custom
 * property — changing the palette means changing these two lines with it.
 *
 * Static by design: nothing here is request-time, so this route stays cached.
 */
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: STORE_BRAND.name,
    short_name: STORE_BRAND.shortName,
    description: STORE_BRAND.standfirst,
    start_url: '/',
    display: 'standalone',
    background_color: '#F0E7D8',
    theme_color: '#0B3D1C',
    icons: [
      { src: '/favicon.ico', sizes: '48x48 32x32 16x16', type: 'image/x-icon' },
      { src: '/apple-icon.png', sizes: '180x180', type: 'image/png' },
      { src: '/icon.png', sizes: '512x512', type: 'image/png' },
      /*
       * The same mark inset further, for a launcher that crops the icon to its own shape. Without
       * a maskable entry Android draws the square tile shrunk inside a white circle; with one it
       * fills the shape, which is why the inset has to leave the middle 80% clear.
       */
      {
        src: '/icon-maskable.png',
        sizes: '512x512',
        type: 'image/png',
        purpose: 'maskable',
      },
    ],
  }
}
