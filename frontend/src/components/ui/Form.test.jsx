import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { FormField } from './Form'

describe('FormField', () => {
  it('renders labelled fields and descriptions', () => {
    render(
      <FormField label="Group name" htmlFor="group-name" description="Pick something short">
        <input id="group-name" />
      </FormField>,
    )

    expect(screen.getByLabelText('Group name')).toBeInTheDocument()
    expect(screen.getByText('Pick something short')).toBeInTheDocument()
  })

  it('announces validation errors', () => {
    render(
      <FormField label="Group name" error="Too short">
        <input />
      </FormField>,
    )

    expect(screen.getByRole('alert')).toHaveTextContent('Too short')
  })
})
