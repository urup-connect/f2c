import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { CATALOGUE_LIST } from '@/lib/strain-catalogue-content'
import type { StrainRow } from '@/lib/strain-catalogue'
import { CatalogueScreen } from './CatalogueScreen'

/*
 * The catalogue list.
 *
 * `listStrains` is mocked. What is under test is the screen's behaviour around
 * three properties, each of which is a way an administrator could be misled.
 *
 * **An empty catalogue and an empty filter are never the same sentence.** "The
 * catalogue holds no strains yet" shown beside a filter somebody set sends them
 * looking for data that is there.
 *
 * **A failed read is never reported as zero strains.** Same reasoning as
 * `readPasskeys`: somebody told they have none will go and create them.
 *
 * **Filtering re-queries rather than filtering an array.** The list is
 * unpaginated today, and a browser-side filter would be filtering one page and
 * calling it the catalogue the moment that changes.
 */

const { listStrains } = vi.hoisted(() => ({ listStrains: vi.fn() }))

vi.mock('@/lib/strain-catalogue-api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/strain-catalogue-api')>()),
  listStrains,
}))

const row = (overrides: Partial<StrainRow> = {}): StrainRow => ({
  id: 'strain-1',
  name: 'OG Kush',
  slug: 'og-kush',
  status: 'active',
  strain_type: 'hybrid',
  reserved_to: null,
  listings_live: 0,
  listings_total: 0,
  updated_at: '2026-08-01T09:00:00Z',
  ...overrides,
})

const setup = (
  initial: readonly StrainRow[] = [row()],
  unavailable = false,
) => {
  render(
    <CatalogueScreen
      initial={initial}
      unavailable={unavailable}
      strainHref={(id) => `/admin/strains/${id}`}
      addHref="/admin/strains/new"
      termsHref="/admin/strains/terms"
    />,
  )
}

beforeEach(() => {
  listStrains.mockReset()
  listStrains.mockResolvedValue([])
})

describe('the first paint', () => {
  test('draws what the server rendered without fetching', () => {
    // An administrator should never see the catalogue they opened render blank
    // for a frame; that reads as though the club had lost it.
    setup([row({ name: 'OG Kush' })])

    expect(screen.getByRole('link', { name: 'OG Kush' })).toBeInTheDocument()
    expect(listStrains).not.toHaveBeenCalled()
  })

  test('links each strain by its name', () => {
    // The name is the link, so the click target is the thing that identifies the
    // row -- rather than an "Edit" cell at the far right of a table that scrolls.
    setup([row({ id: 'abc', name: 'Cheese' })])

    expect(screen.getByRole('link', { name: 'Cheese' })).toHaveAttribute(
      'href',
      '/admin/strains/abc',
    )
  })

  test('labels every column', () => {
    setup()

    for (const label of [
      CATALOGUE_LIST.columnName,
      CATALOGUE_LIST.columnType,
      CATALOGUE_LIST.columnStatus,
      CATALOGUE_LIST.columnReserved,
      CATALOGUE_LIST.columnOffers,
      CATALOGUE_LIST.columnUpdated,
    ]) {
      expect(screen.getByRole('columnheader', { name: label })).toBeInTheDocument()
    }
  })

  test('offers a way to add a strain and a way to the vocabularies', () => {
    setup()

    expect(screen.getByRole('link', { name: CATALOGUE_LIST.addLabel })).toHaveAttribute(
      'href',
      '/admin/strains/new',
    )
    expect(
      screen.getByRole('link', { name: CATALOGUE_LIST.termsLabel }),
    ).toHaveAttribute('href', '/admin/strains/terms')
  })
})

describe('what each row says', () => {
  test('marks a strain that members cannot see', () => {
    // Three of the four statuses keep a strain out of the catalogue and nothing
    // about the label says which.
    setup([row({ status: 'hidden' })])

    expect(screen.getByText(CATALOGUE_LIST.notBrowsable)).toBeInTheDocument()
  })

  test('does not mark an active strain', () => {
    setup([row({ status: 'active' })])

    expect(screen.queryByText(CATALOGUE_LIST.notBrowsable)).not.toBeInTheDocument()
  })

  test('says an unreserved strain is open to all rather than showing a dash', () => {
    setup([row({ reserved_to: null })])

    expect(screen.getByText(CATALOGUE_LIST.openToAll)).toBeInTheDocument()
  })

  test('names the cultivator a strain is reserved to', () => {
    setup([row({ reserved_to: 'Kloof' })])

    expect(screen.getByText('Kloof')).toBeInTheDocument()
  })

  test('shows both offer counts, because a retirement turns on the gap', () => {
    setup([row({ listings_live: 1, listings_total: 3 })])

    expect(
      screen.getByText(`1 ${CATALOGUE_LIST.offersSummary} 3`),
    ).toBeInTheDocument()
  })

  test('shows the date without the time, and keeps the machine value', () => {
    setup([row({ updated_at: '2026-08-01T09:00:00Z' })])

    const stamp = screen.getByText('2026-08-01')

    expect(stamp.tagName).toBe('TIME')
    expect(stamp).toHaveAttribute('datetime', '2026-08-01T09:00:00Z')
  })

  test('translates the type into words', () => {
    setup([row({ strain_type: 'sativa' })])

    // Scoped to the table: "Sativa" is also an option in the type filter above
    // it, which is the same word doing a different job.
    expect(
      screen.getByRole('cell', { name: 'Sativa' }),
    ).toBeInTheDocument()
  })
})

describe('filtering', () => {
  test('re-queries the API rather than filtering the rows on screen', async () => {
    setup()

    await userEvent.selectOptions(
      screen.getByRole('combobox', { name: CATALOGUE_LIST.statusLabel }),
      'pending',
    )

    await waitFor(() =>
      expect(listStrains).toHaveBeenCalledWith(
        expect.objectContaining({ status: 'pending' }),
      ),
    )
  })

  test('sends the type filter', async () => {
    setup()

    await userEvent.selectOptions(
      screen.getByRole('combobox', { name: CATALOGUE_LIST.typeLabel }),
      'indica',
    )

    await waitFor(() =>
      expect(listStrains).toHaveBeenCalledWith(
        expect.objectContaining({ strain_type: 'indica' }),
      ),
    )
  })

  test('searches as the administrator types', async () => {
    // A search box that waits for blur has somebody type a name, see nothing
    // happen, and click elsewhere to find out whether it worked.
    setup()

    await userEvent.type(
      screen.getByRole('searchbox', { name: CATALOGUE_LIST.searchLabel }),
      'kush',
    )

    await waitFor(() =>
      expect(listStrains).toHaveBeenLastCalledWith(
        expect.objectContaining({ search: 'kush' }),
      ),
    )
  })

  test('carries the other filters when one changes', async () => {
    // The bug this guards: reading state that a `setState` in the same tick has
    // not landed yet, so the second filter queries with the first one missing.
    setup()

    await userEvent.selectOptions(
      screen.getByRole('combobox', { name: CATALOGUE_LIST.statusLabel }),
      'pending',
    )
    await userEvent.selectOptions(
      screen.getByRole('combobox', { name: CATALOGUE_LIST.typeLabel }),
      'indica',
    )

    await waitFor(() =>
      expect(listStrains).toHaveBeenLastCalledWith({
        status: 'pending',
        strain_type: 'indica',
        search: '',
      }),
    )
  })

  test('replaces the rows with what came back', async () => {
    listStrains.mockResolvedValue([row({ id: 'other', name: 'Durban Poison' })])
    setup([row({ name: 'OG Kush' })])

    await userEvent.selectOptions(
      screen.getByRole('combobox', { name: CATALOGUE_LIST.statusLabel }),
      'pending',
    )

    expect(
      await screen.findByRole('link', { name: 'Durban Poison' }),
    ).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'OG Kush' })).not.toBeInTheDocument()
  })

  test('offers a way to clear, only once something is set', async () => {
    setup()

    expect(
      screen.queryByRole('button', { name: CATALOGUE_LIST.clearLabel }),
    ).not.toBeInTheDocument()

    await userEvent.selectOptions(
      screen.getByRole('combobox', { name: CATALOGUE_LIST.statusLabel }),
      'pending',
    )

    expect(
      await screen.findByRole('button', { name: CATALOGUE_LIST.clearLabel }),
    ).toBeInTheDocument()
  })

  test('clearing resets every filter and re-queries unfiltered', async () => {
    setup()

    await userEvent.selectOptions(
      screen.getByRole('combobox', { name: CATALOGUE_LIST.statusLabel }),
      'pending',
    )
    await userEvent.click(
      await screen.findByRole('button', { name: CATALOGUE_LIST.clearLabel }),
    )

    await waitFor(() =>
      expect(listStrains).toHaveBeenLastCalledWith({
        status: '',
        strain_type: '',
        search: '',
      }),
    )
    expect(
      screen.getByRole('combobox', { name: CATALOGUE_LIST.statusLabel }),
    ).toHaveValue('')
  })
})

describe('an empty list', () => {
  test('says the catalogue is empty when nothing is filtered', () => {
    setup([])

    expect(screen.getByText(CATALOGUE_LIST.empty)).toBeInTheDocument()
  })

  test('says the filter matched nothing when something is filtered', async () => {
    // The two sentences send an administrator to two different places.
    setup([])

    await userEvent.selectOptions(
      screen.getByRole('combobox', { name: CATALOGUE_LIST.statusLabel }),
      'pending',
    )

    expect(await screen.findByText(CATALOGUE_LIST.emptyFiltered)).toBeInTheDocument()
    expect(screen.queryByText(CATALOGUE_LIST.empty)).not.toBeInTheDocument()
  })

  test('draws no table', () => {
    setup([])

    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })
})

describe('when the read fails', () => {
  test('says so rather than reporting an empty catalogue', () => {
    setup([], true)

    expect(screen.getByRole('alert')).toHaveTextContent(CATALOGUE_LIST.loadFailed)
  })

  test('a failed re-query keeps the rows that were on screen', async () => {
    // They are stale rather than wrong, and a table replaced by an error message
    // loses the administrator's place in a list they were reading.
    listStrains.mockRejectedValue(new Error('down'))
    setup([row({ name: 'OG Kush' })])

    await userEvent.selectOptions(
      screen.getByRole('combobox', { name: CATALOGUE_LIST.statusLabel }),
      'pending',
    )

    expect(await screen.findByRole('alert')).toHaveTextContent(
      CATALOGUE_LIST.loadFailed,
    )
    expect(screen.getByRole('link', { name: 'OG Kush' })).toBeInTheDocument()
  })

  test('a later success clears the message', async () => {
    listStrains.mockRejectedValueOnce(new Error('down'))
    listStrains.mockResolvedValue([row({ name: 'Cheese' })])
    setup([row()])

    await userEvent.selectOptions(
      screen.getByRole('combobox', { name: CATALOGUE_LIST.statusLabel }),
      'pending',
    )
    await screen.findByRole('alert')

    await userEvent.selectOptions(
      screen.getByRole('combobox', { name: CATALOGUE_LIST.typeLabel }),
      'indica',
    )

    await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument())
  })
})
