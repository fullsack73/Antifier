import { fireEvent, render, screen } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import { expect, it, vi } from 'vitest'
import CandidateSearchSettings, { CandidateSearchSummary } from '../src/frontend/CandidateSearchSettings.jsx'
import { DEFAULT_CANDIDATE_SEARCH } from '../src/frontend/candidateSearchDefaults.js'

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: key => key }) }))

it('defaults to 252 sessions and exposes all three search modes', () => {
  const onChange=vi.fn()
  render(<CandidateSearchSettings value={DEFAULT_CANDIDATE_SEARCH} onChange={onChange} />)
  expect(screen.getByLabelText('candidateSearch.refresh_interval')).toHaveValue(252)
  fireEvent.change(screen.getByLabelText('candidateSearch.mode'),{ target:{value:'frozen_forecast'} })
  expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ mode:'frozen_forecast', enabled:true }))
})

it('GMV displays price mode and disables the forecast-only refresh control', () => {
  render(<CandidateSearchSettings riskOnly onChange={vi.fn()} />)
  expect(screen.getByLabelText('candidateSearch.mode')).toHaveValue('price_features')
  expect(screen.getByLabelText('candidateSearch.mode')).toBeDisabled()
  expect(screen.getByLabelText('candidateSearch.refresh_interval')).toBeDisabled()
})

it('identifies legacy results without applying the new default retrospectively', () => {
  render(<CandidateSearchSummary />)
  expect(screen.getByText('candidateSearch.legacy')).toBeInTheDocument()
})
