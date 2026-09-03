import { render, screen } from '@testing-library/react'
import { describe, expect, test } from 'vitest'
import { BRAND_FILM, brandFilmPoster, brandFilmSource } from '@/lib/brand-film'
import { FILM } from '@/lib/landing-content'
import { siteConfig } from '@/lib/site'
import { ClubFilm } from './ClubFilm'

/* design/features/landing.md sections 3 and 5. */

const film = (container: HTMLElement) => {
  const element = container.querySelector('video')
  if (!element) throw new Error('ClubFilm rendered no video element')
  return element
}

describe('ClubFilm', () => {
  test('is headed at level two, below the page heading', () => {
    render(<ClubFilm />)

    expect(screen.getByRole('heading', { level: 2, name: FILM.heading })).toBeInTheDocument()
  })

  test('is a landmark named by its own heading', () => {
    render(<ClubFilm />)

    expect(screen.getByRole('region', { name: FILM.heading })).toBeInTheDocument()
  })

  test('serves the film from the deployment CDN, never from a hardcoded host', () => {
    const { container } = render(<ClubFilm />)

    expect(film(container)).toHaveAttribute('src', brandFilmSource(siteConfig()))
  })

  test('plays nothing on its own, and offers controls to a reader who wants it', () => {
    /*
     * WCAG 2.2.2. The film runs a minute and carries a soundtrack, so anything that started by
     * itself would need a pause control. Not starting is simpler and serves everyone.
     */
    const { container } = render(<ClubFilm />)
    const video = film(container)

    expect(video).not.toHaveAttribute('autoplay')
    expect(video).not.toHaveAttribute('loop')
    expect(video.controls).toBe(true)
  })

  test('shows the still frame from the CDN before anything is played', () => {
    const { container } = render(<ClubFilm />)

    expect(film(container)).toHaveAttribute('poster', brandFilmPoster(siteConfig()))
  })

  test('fetches the header rather than seven megabytes nobody asked for', () => {
    const { container } = render(<ClubFilm />)

    expect(film(container)).toHaveAttribute('preload', 'metadata')
  })

  test('stays inline on a phone rather than taking the screen over', () => {
    const { container } = render(<ClubFilm />)

    expect(film(container).playsInline).toBe(true)
  })

  test('reserves the film box from the manifest, so the page does not reflow when it loads', () => {
    const { container } = render(<ClubFilm />)
    const video = film(container)

    expect(video).toHaveAttribute('width', String(BRAND_FILM.width))
    expect(video).toHaveAttribute('height', String(BRAND_FILM.height))
    expect(video.parentElement?.style.aspectRatio).toBe(
      `${BRAND_FILM.width} / ${BRAND_FILM.height}`,
    )
  })

  test('offers no caption track while the one on the CDN is a placeholder', () => {
    /*
     * A track pointing at placeholder cues is worse than none: the moment the host's MIME type
     * and CORS headers are corrected, "[Caption text for the first line of dialogue/narration]"
     * appears over the film. See design/features/landing.md risk 4.
     */
    const { container } = render(<ClubFilm />)

    expect(container.querySelector('track')).toBeNull()
  })

  test('is named by the section heading, so its name is copy the compliance tests hold', () => {
    const { container } = render(<ClubFilm />)

    const labelledBy = film(container).getAttribute('aria-labelledby')
    expect(labelledBy).toBeTruthy()
    expect(container.querySelector(`#${labelledBy}`)).toHaveTextContent(FILM.heading)
  })
})
