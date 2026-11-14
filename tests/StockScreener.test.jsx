import { fireEvent, render, screen, cleanup, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { afterEach, expect, it, vi } from 'vitest';
import StockScreener from '../src/frontend/StockScreener.jsx';

vi.mock('react-i18next', () => ({
    useTranslation: () => ({
        t: (key, values) => key === 'stockScreener.partialCoverage'
            ? `${values.fetched}/${values.requested} analyzed, ${values.missing} missing`
            : key,
    }),
}));

afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
});

it('shows partial coverage alongside matching rows and clears it after a complete retry', async () => {
    const rows = [{ Ticker: 'MSFT', Company: 'Microsoft', 'Financial Score': 82 }];
    const fetchMock = vi.fn()
        .mockResolvedValueOnce({ ok: true, json: async () => ({
            results: rows, coverage: { requested: 3, fetched: 1, missing: 2 },
        }) })
        .mockResolvedValueOnce({ ok: true, json: async () => ({
            results: rows, coverage: { requested: 3, fetched: 3, missing: 0 },
        }) });
    vi.stubGlobal('fetch', fetchMock);
    render(<StockScreener />);
    fireEvent.click(screen.getByRole('button', { name: 'stockScreener.searchStocks' }));
    expect(await screen.findByRole('status')).toHaveTextContent('1/3 analyzed, 2 missing');
    expect(screen.getByText('MSFT')).toBeInTheDocument();
    expect(JSON.parse(fetchMock.mock.calls[0][1].body).include_coverage).toBe(true);
    fireEvent.click(screen.getByRole('button', { name: 'stockScreener.searchStocks' }));
    expect(await screen.findByText('MSFT')).toBeInTheDocument();
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
});


it('accepts the legacy array response without crashing', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
        ok: true, json: async () => [{ Ticker: 'AGX', Company: 'Argan' }],
    }));
    render(<StockScreener />);
    fireEvent.click(screen.getByRole('button', { name: 'stockScreener.searchStocks' }));
    expect(await screen.findByText('Argan')).toBeInTheDocument();
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
});

it.each([{ data: null }, { data: {} }, { data: { results: null } }])(
    'shows an error for malformed successful responses: $data', async ({ data }) => {
        vi.spyOn(console, 'error').mockImplementation(() => {});
        vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => data }));
        render(<StockScreener />);
        fireEvent.click(screen.getByRole('button', { name: 'stockScreener.searchStocks' }));
        expect(await screen.findByText('stockScreener.fetchError')).toBeInTheDocument();
        expect(screen.getByRole('button', { name: 'stockScreener.searchStocks' })).toBeEnabled();
    },
);

it('deduplicates uploaded ticker symbols before displaying and submitting them', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => [] });
    vi.stubGlobal('fetch', fetchMock);
    const consoleError = vi.spyOn(console, 'error');
    const { container } = render(<StockScreener />);
    fireEvent.change(screen.getAllByRole('combobox')[0], { target: { value: 'Custom' } });
    fireEvent.change(container.querySelector('input[type="file"]'), {
        target: { files: [new File(['Symbol\nAGX\nagx\nAII\nAII'], 'tickers.csv', { type: 'text/csv' })] },
    });
    expect(await screen.findByText('AGX')).toBeInTheDocument();
    expect(screen.getAllByText('AGX')).toHaveLength(1);
    expect(screen.getAllByText('AII')).toHaveLength(1);
    expect(consoleError).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'common.done' }));
    fireEvent.click(screen.getByRole('button', { name: 'stockScreener.searchStocks' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'stockScreener.searchStocks' })).toBeEnabled());
    expect(JSON.parse(fetchMock.mock.calls[0][1].body).filters.tickers).toEqual(['AGX', 'AII']);
    expect(consoleError).not.toHaveBeenCalled();
});
