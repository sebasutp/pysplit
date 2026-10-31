import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import '../../services/i18n'
import { Footer } from './Footer'

describe('Footer', () => {
  it('renders the Zurich attribution in English', () => {
    render(<Footer />)

    expect(screen.getByText(/Made in Zurich, Switzerland/)).toBeInTheDocument()
  })
})
