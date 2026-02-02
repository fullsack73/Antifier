import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import '@testing-library/jest-dom'
import Optimizer from './Optimizer'
import { vi } from 'vitest'
import axios from 'axios'
import userEvent from '@testing-library/user-event'

// Mock axios
vi.mock('axios')

// Mock react-i18next
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key) => {
        const translations = {
            "optimizer.title": "Portfolio Optimizer",
            "optimizer.tickerGroup": "Ticker Group",
            "optimizer.loadPortfolio": "Load JSON",
            "optimizer.modelStrategy": "Model Strategy",
            "common.starting": "Starting...",
        }
        return translations[key] || key
    }
  })
}))

describe('Optimizer Component - Model Selection', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  test('renders Model Strategy dropdown', () => {
    render(<Optimizer />)
    expect(screen.getByText('Model Strategy')).toBeInTheDocument()
    // Default value should be BL
    const select = screen.getByRole('combobox', { name: /model strategy/i })
    expect(select.value).toBe('BL')
  })

  test('can select different model strategies', async () => {
    const user = userEvent.setup()
    render(<Optimizer />)
    
    const select = screen.getByRole('combobox', { name: /model strategy/i })
    
    // Select Deep Learning Ensemble
    await user.selectOptions(select, 'Ensemble')
    expect(select.value).toBe('Ensemble')
    
    // Select Lightweight
    await user.selectOptions(select, 'Lightweight')
    expect(select.value).toBe('Lightweight')

    // Select MPT
    await user.selectOptions(select, 'MPT')
    expect(select.value).toBe('MPT')
  })

  test('includes model_strategy in submission payload', async () => {
    const user = userEvent.setup()
    render(<Optimizer />)
    
    // Set up SSE mock if needed, but for now we focus on axios call
    // Mock EventSource globally
    global.EventSource = vi.fn(function() {
        return {
            addEventListener: vi.fn(),
            close: vi.fn(),
            onmessage: null
        }
    })

    // Fill in required fields to trigger submit
    // Assuming defaults or basic inputs are enough to not crash, 
    // but in a real app we might need to fill more.
    // The component might have "required" fields.
    // Let's assume startDate and endDate are needed.
    
    const userInputs = [
        { label: /Start Date/i, value: '2023-01-01' },
        { label: /End Date/i, value: '2023-12-31' }
    ]

    // Depending on how Optimizer is implemented, we might need value setters.
    // For now, let's just select the model strategy and submit.
    // If the form prevents default on missing fields, this test might fail without filling them.
    // However, the user task is focused on the model selection.
    
    const select = screen.getByRole('combobox', { name: /model strategy/i })
    await user.selectOptions(select, 'MPT')

    // Fill required fields
    // startDate
    // Note: getByLabel/Role for dates might be tricky if labels aren't linked or translations differ.
    // Let's use getByLabelText assuming labels are correct or querySelector if needed.
    // The translation mocks are: "optimizer.startDate": "optimizer.startDate" (from my mock if key not found)
    // Wait, my mock translation function:
    /*
        const translations = {
            "optimizer.title": "Portfolio Optimizer",
            "optimizer.tickerGroup": "Ticker Group",
            "optimizer.loadPortfolio": "Load JSON",
            "optimizer.modelStrategy": "Model Strategy",
            "common.starting": "Starting...",
        }
        return translations[key] || key
    */
    
    // So "optimizer.startDate" returns "optimizer.startDate".
    // AND in Optimizer.jsx: <label>{t("optimizer.startDate")}</label>
    // But labels are NOT linked to inputs for startDate/endDate in the code I read earlier!
    
    /*
          <div className="optimizer-form-group">
            <label>{t("optimizer.startDate")}</label>
            <input
              className="optimizer-input"
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              required
            />
          </div>
    */
    
    // So I can't use getByLabelText easily.
    // I can try to find by specific selector or just use getByDisplayValue if I set it? No.
    // I will use getAllByRole('textbox')? No, type="date" might not be textbox role.
    // I will use container.querySelector or similar if needed, but testing library prefers accessibility.
    // Since I'm supposed to be an expert UI designer, maybe I should fix the accessibility for Date inputs too?
    // But that's scope creep.
    // I will use `container.querySelectorAll('input[type="date"]')`.
    
    const dateInputs = screen.getAllByDisplayValue('') // This might be too broad.
    // Let's rely on the order or something.
    // OR just use fireEvent on the inputs found by placeholder if any? No placeholder.
    
    // Let's fix the test by getting elements by index or selector.
    const inputs = document.body.querySelectorAll('input[type="date"]')
    // 0 is start, 1 is end
    await fireEvent.change(inputs[0], { target: { value: '2023-01-01' } })
    await fireEvent.change(inputs[1], { target: { value: '2023-12-31' } })
    
    const submitBtn = screen.getByRole('button', { name: /optimize|submit/i })
    fireEvent.click(submitBtn)

    await waitFor(() => {
      expect(axios.post).toHaveBeenCalled()
      const payload = axios.post.mock.calls[0][1]
      expect(payload).toHaveProperty('model_strategy', 'MPT')
    })
  })
})
