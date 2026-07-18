import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { Pagination } from './Pagination'

/**
 * The point of this pager is the one thing an ordinary Previous/Next lacks: jumping
 * to a far page without walking there. That jump lives in the editable current cell,
 * so most of these tests exercise it -- typing a page, clamping a bad one, and the two
 * ways to abandon an edit -- because a silent regression there is the pager failing at
 * the only job it was built for.
 */

describe('Pagination', () => {
  it('renders nothing for a single page', () => {
    const { container } = render(<Pagination page={1} totalPages={1} onPage={vi.fn()} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('shows a window of numbers with the current page as an editable field', () => {
    render(<Pagination page={3} totalPages={157} onPage={vi.fn()} />)
    // 1,2,4,5 are buttons; 3 is the input -- so it is NOT a button.
    expect(screen.getByRole('button', { name: 'Go to page 4' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Go to page 3' })).not.toBeInTheDocument()
    expect(screen.getByRole('textbox')).toHaveValue('3')
  })

  it('clicking a number cell navigates to it', async () => {
    const onPage = vi.fn()
    render(<Pagination page={3} totalPages={157} onPage={onPage} />)
    await userEvent.click(screen.getByRole('button', { name: 'Go to page 5' }))
    expect(onPage).toHaveBeenCalledWith(5)
  })

  it('Previous and Next step one page, and stop at the ends', async () => {
    const onPage = vi.fn()
    const { rerender } = render(<Pagination page={3} totalPages={157} onPage={onPage} />)
    await userEvent.click(screen.getByRole('button', { name: 'Previous' }))
    await userEvent.click(screen.getByRole('button', { name: 'Next' }))
    expect(onPage.mock.calls).toEqual([[2], [4]])

    rerender(<Pagination page={1} totalPages={157} onPage={onPage} />)
    expect(screen.getByRole('button', { name: 'Previous' })).toBeDisabled()
    rerender(<Pagination page={157} totalPages={157} onPage={onPage} />)
    expect(screen.getByRole('button', { name: 'Next' })).toBeDisabled()
  })

  it('editing the current page and pressing Enter jumps there', async () => {
    const onPage = vi.fn()
    render(<Pagination page={3} totalPages={157} onPage={onPage} />)
    const input = screen.getByRole('textbox')
    await userEvent.clear(input)
    await userEvent.type(input, '10{Enter}')
    expect(onPage).toHaveBeenCalledWith(10)
  })

  it('committing on blur jumps too -- Enter is not the only trigger', async () => {
    const onPage = vi.fn()
    render(<Pagination page={3} totalPages={157} onPage={onPage} />)
    const input = screen.getByRole('textbox')
    await userEvent.clear(input)
    await userEvent.type(input, '42')
    await userEvent.tab() // blur
    expect(onPage).toHaveBeenCalledWith(42)
  })

  it('clamps a page past the end to the last page', async () => {
    const onPage = vi.fn()
    render(<Pagination page={3} totalPages={157} onPage={onPage} />)
    const input = screen.getByRole('textbox')
    await userEvent.clear(input)
    await userEvent.type(input, '999{Enter}')
    expect(onPage).toHaveBeenCalledWith(157)
  })

  it('clamps a below-one page up to page one', async () => {
    const onPage = vi.fn()
    render(<Pagination page={3} totalPages={157} onPage={onPage} />)
    const input = screen.getByRole('textbox')
    await userEvent.clear(input)
    await userEvent.type(input, '0{Enter}')
    expect(onPage).toHaveBeenCalledWith(1)
  })

  it('ignores non-digits while typing', async () => {
    const onPage = vi.fn()
    render(<Pagination page={3} totalPages={157} onPage={onPage} />)
    const input = screen.getByRole('textbox')
    await userEvent.clear(input)
    await userEvent.type(input, '1a2b{Enter}')
    expect(onPage).toHaveBeenCalledWith(12)
  })

  it('Escape abandons the edit without navigating', async () => {
    const onPage = vi.fn()
    render(<Pagination page={3} totalPages={157} onPage={onPage} />)
    const input = screen.getByRole('textbox')
    await userEvent.clear(input)
    await userEvent.type(input, '99{Escape}')
    expect(onPage).not.toHaveBeenCalled()
    expect(input).toHaveValue('3')
  })

  it('an emptied field reverts instead of navigating', async () => {
    const onPage = vi.fn()
    render(<Pagination page={3} totalPages={157} onPage={onPage} />)
    const input = screen.getByRole('textbox')
    await userEvent.clear(input)
    await userEvent.type(input, '{Enter}')
    expect(onPage).not.toHaveBeenCalled()
    expect(input).toHaveValue('3')
  })

  it('re-typing the same page does not fire a navigation', async () => {
    const onPage = vi.fn()
    render(<Pagination page={3} totalPages={157} onPage={onPage} />)
    const input = screen.getByRole('textbox')
    await userEvent.clear(input)
    await userEvent.type(input, '3{Enter}')
    expect(onPage).not.toHaveBeenCalled()
  })
})
