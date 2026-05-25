import { render, screen } from '@testing-library/react'
import { Badge } from './badge'
import { describe, it, expect } from 'vitest'

describe('Badge Component', () => {
  it('renders the badge with text', () => {
    render(<Badge>Test Badge</Badge>)
    const badge = screen.getByText('Test Badge')
    expect(badge).toBeInTheDocument()
  })

  it('applies default variant classes', () => {
    render(<Badge data-testid="badge">Default</Badge>)
    const badge = screen.getByTestId('badge')
    expect(badge).toHaveClass('bg-primary')
  })

  it('applies destructive variant classes', () => {
    render(<Badge data-testid="badge" variant="destructive">Destructive</Badge>)
    const badge = screen.getByTestId('badge')
    expect(badge).toHaveClass('bg-destructive')
  })
})
