import { useState, useCallback, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { apiUrl } from './apiClient.js';
import './App.css';

// Define available metrics
// Matches backend keys
const METRICS = [
    { value: 'P/E', label: 'P/E Ratio' },
    { value: 'Forward P/E', label: 'Forward P/E' },
    { value: 'P/B', label: 'Price/Book (P/B)' },
    { value: 'Price/Sales', label: 'Price/Sales (P/S)' },
    { value: 'PEG', label: 'PEG Ratio' },
    { value: 'Debt/Equity', label: 'Debt/Equity' },
    { value: 'ROE', label: 'Return on Equity (ROE)' },
    { value: 'ROA', label: 'Return on Assets (ROA)' },
    { value: 'Profit Margin', label: 'Profit Margin' },
    { value: 'Market Cap', label: 'Market Cap' },
    { value: 'Price', label: 'Current Price' },
];

const OPERATORS = [
    { value: 'Under', label: 'Under (<)' },
    { value: 'Over', label: 'Over (>)' },
    { value: 'Equals', label: 'Equals (=)' },
];

const StockScreener = () => {
    const { t } = useTranslation();
    const [tickerGroup, setTickerGroup] = useState('S&P 500');
    const [filters, setFilters] = useState([
        { metric: 'P/E', operator: 'Under', value: '15' },
    ]);
    const [results, setResults] = useState([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);
    const [customTickers, setCustomTickers] = useState([]);
    const [uploadFileName, setUploadFileName] = useState('');
    const [uploadError, setUploadError] = useState(null);
    const [showUploadModal, setShowUploadModal] = useState(false);
    const fileInputRef = useRef(null);

    const handleAddFilter = () => {
        setFilters([...filters, { metric: 'P/E', operator: 'Under', value: '' }]);
    };

    const handleRemoveFilter = (index) => {
        setFilters(filters.filter((_, i) => i !== index));
    };

    const handleFilterChange = (index, field, value) => {
        const newFilters = filters.map((filter, i) =>
            i === index ? { ...filter, [field]: value } : filter
        );
        setFilters(newFilters);
    };

    const handleFileUpload = (e) => {
        const file = e.target.files[0];
        if (!file) return;

        setUploadError(null);
        setUploadFileName(file.name);

        if (!file.name.toLowerCase().endsWith('.csv')) {
            setUploadError('Only .csv files are accepted.');
            setCustomTickers([]);
            setUploadFileName('');
            e.target.value = '';
            return;
        }

        const reader = new FileReader();
        reader.onload = (event) => {
            const text = event.target.result;
            const tickers = text
                .split(/[\r\n,]+/)
                .map(t => t.trim())
                // Remove header rows, RTF artifacts, and empty lines
                .filter(t => t && !t.startsWith('\\') && !t.startsWith('{') && !t.startsWith('}'))
                .filter(t => !/^(symbol|ticker|name|company)$/i.test(t))
                .map(t => t.replace(/\\$/, ''))
                // Allow only valid ticker characters: letters, digits, dots, hyphens, carets
                .filter(t => /^[A-Z0-9.\-^]+$/i.test(t));

            if (tickers.length === 0) {
                setUploadError('No valid ticker symbols found in the file.');
                setCustomTickers([]);
            } else {
                setCustomTickers(tickers);
            }
        };
        reader.onerror = () => {
            setUploadError('Failed to read the file.');
            setCustomTickers([]);
        };
        reader.readAsText(file);
        // Reset input so the same file can be re-uploaded
        e.target.value = '';
    };

    const handleClearUpload = () => {
        setCustomTickers([]);
        setUploadFileName('');
        setUploadError(null);
        if (fileInputRef.current) fileInputRef.current.value = '';
    };

    const handleCloseUploadModal = () => {
        setShowUploadModal(false);
        // If no tickers loaded, revert to default universe
        if (customTickers.length === 0) {
            setTickerGroup('S&P 500');
        }
    };

    const handleSearch = useCallback(async () => {
        setLoading(true);
        setError(null);
        setResults([]);

        // Construct API payload
        // If Custom, we probably need a way to send the custom list to the backend
        // For now, let's assume 'tickerGroup' handles the predefined ones.
        // For 'Custom', the backend might not be ready to accept a raw list of strings in the body yet based on my implementation.
        // My backend uses `get_ticker_group`. I'll stick to predefined groups for now as per "exhaustive search" request.

        if (tickerGroup === 'Custom' && customTickers.length === 0) {
            setError('Please upload a CSV file with valid ticker symbols.');
            setLoading(false);
            return;
        }

        const payload = {
            filters: {
                Index: tickerGroup,
                criteria: filters
            }
        };

        // When using custom tickers, send them to the backend
        if (tickerGroup === 'Custom') {
            payload.filters.tickers = customTickers;
        }

        try {
            const response = await fetch(apiUrl('/api/stock-screener'), {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(payload),
            });

            if (!response.ok) {
                const errData = await response.json();
                throw new Error(errData.error || 'Network response was not ok');
            }

            const data = await response.json();
            setResults(data);
        } catch (err) {
            setError(err.message || 'Failed to fetch screener results.');
            if (import.meta.env.DEV) {
                console.error(err);
            }
        } finally {
            setLoading(false);
        }
    }, [filters, tickerGroup, customTickers]);

    const handleDownloadCSV = () => {
        if (results.length === 0) return;

        // Only export ticker symbols to match portfolio optimizer format (like nyse.csv)
        const csvData = ['Symbol', ...results.map(row => row.Ticker)].join('\n');

        const encodedUri = 'data:text/csv;charset=utf-8,' + encodeURIComponent(csvData);
        const link = document.createElement('a');
        link.setAttribute('href', encodedUri);
        link.setAttribute('download', 'stock-screener-results.csv');
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
    };

    // Helper to format currency/percent
    const formatValue = (key, val) => {
        if (val === null || val === undefined) return '-';
        if (key.includes('Cap') || key === 'Price') {
            // Basic formatter for large numbers
            if (val > 1e9) return `$${(val / 1e9).toFixed(2)}B`;
            if (val > 1e6) return `$${(val / 1e6).toFixed(2)}M`;
            return `$${val.toFixed(2)}`;
        }
        if (['P/E', 'Forward P/E', 'P/B', 'Price/Sales', 'PEG'].includes(key)) {
            return parseFloat(val).toFixed(2);
        }
        if (['ROE', 'ROA', 'Profit Margin'].includes(key)) {
            return `${(val * 100).toFixed(2)}%`; // Assuming backend returns 0.15 for 15%
        }
        return val;
    };

    return (
        <div className="stock-screener-container">
            <h2 className="page-header">{t('stockScreener.stock_screener')}</h2>

            <div className="screener-controls-card">
                <div className="control-header">
                    <h3>Screening Criteria</h3>
                    <div className="universe-selector">
                        <label>Universe:</label>
                        {tickerGroup === 'Custom' && customTickers.length > 0 ? (
                            <button
                                type="button"
                                className="premium-select"
                                onClick={() => setShowUploadModal(true)}
                                style={{ cursor: 'pointer', textAlign: 'left' }}
                            >
                                {uploadFileName} ({customTickers.length})
                            </button>
                        ) : (
                            <select
                                className="premium-select"
                                value={tickerGroup}
                                onChange={(e) => {
                                    setTickerGroup(e.target.value);
                                    if (e.target.value === 'Custom') {
                                        setShowUploadModal(true);
                                    } else {
                                        handleClearUpload();
                                    }
                                }}
                            >
                                <option value="S&P 500">S&P 500</option>
                                <option value="Dow Jones">Dow Jones</option>
                                <option value="Custom">Custom (CSV)</option>
                            </select>
                        )}
                    </div>
                </div>

                <div className="filters-list">
                    {filters.map((filter, index) => (
                        <div key={index} className="filter-row fade-in">
                            <select
                                className="premium-select metric-select"
                                value={filter.metric}
                                onChange={(e) => handleFilterChange(index, 'metric', e.target.value)}
                            >
                                {METRICS.map(m => <option key={m.value} value={m.value}>{m.label}</option>)}
                            </select>
                            <select
                                className="premium-select operator-select"
                                value={filter.operator}
                                onChange={(e) => handleFilterChange(index, 'operator', e.target.value)}
                            >
                                {OPERATORS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                            </select>
                            <input
                                type="text"
                                className="premium-input value-input"
                                value={filter.value}
                                onChange={(e) => handleFilterChange(index, 'value', e.target.value)}
                                placeholder="Value (e.g. 15)"
                            />
                            <button className="remove-filter-btn" onClick={() => handleRemoveFilter(index)}>
                                ×
                            </button>
                        </div>
                    ))}
                </div>

                <div className="action-row">
                    <button className="secondary-btn" onClick={handleAddFilter}>
                        + Add Filter
                    </button>
                    <button className="primary-btn search-btn" onClick={handleSearch} disabled={loading}>
                        {loading ? 'Screening...' : 'Search Stocks'}
                    </button>
                </div>
            </div>

            {showUploadModal && (
                <div className="optimizer-modal-overlay" onClick={handleCloseUploadModal}>
                    <div className="optimizer-modal-content" onClick={e => e.stopPropagation()}>
                        <div className="optimizer-modal-header">
                            <h3 className="optimizer-modal-title">Upload Custom Tickers</h3>
                            <button type="button" className="optimizer-modal-close" onClick={handleCloseUploadModal}>×</button>
                        </div>
                        <div className="optimizer-modal-body">
                            <p style={{ fontSize: '0.85rem', color: 'var(--color-text-muted)', marginBottom: 'var(--spacing-md)' }}>
                                Upload a .csv file containing ticker symbols (one per line or comma-separated). Header rows like &quot;Symbol&quot; or &quot;Ticker&quot; are automatically ignored.
                            </p>
                            <button
                                type="button"
                                className="secondary-btn"
                                onClick={() => fileInputRef.current?.click()}
                                style={{ width: '100%', marginBottom: 'var(--spacing-md)' }}
                            >
                                {uploadFileName ? 'Change File' : 'Choose CSV File'}
                            </button>
                            <input
                                type="file"
                                accept=".csv"
                                ref={fileInputRef}
                                style={{ display: 'none' }}
                                onChange={handleFileUpload}
                            />
                            {uploadError && (
                                <div style={{ fontSize: '0.85rem', color: 'var(--color-danger)', marginBottom: 'var(--spacing-md)' }}>
                                    {uploadError}
                                </div>
                            )}
                            {customTickers.length > 0 && (
                                <div style={{ fontSize: '0.85rem', color: 'var(--color-text-muted)' }}>
                                    <strong>{uploadFileName}</strong> — {customTickers.length} ticker{customTickers.length !== 1 ? 's' : ''} loaded
                                    <ul className="optimizer-weights-list" style={{ marginTop: 'var(--spacing-sm)', maxHeight: '150px' }}>
                                        {customTickers.map(t => <li key={t}><span>{t}</span></li>)}
                                    </ul>
                                </div>
                            )}
                        </div>
                        <div className="optimizer-modal-footer">
                            {customTickers.length > 0 && (
                                <button type="button" className="secondary-btn" onClick={handleClearUpload}>
                                    Clear
                                </button>
                            )}
                            <button type="button" className="primary-btn" onClick={handleCloseUploadModal}>
                                Done
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {error && <div className="error-banner">{error}</div>}

            {results.length > 0 && (
                <div className="results-section fade-in">
                    <div className="results-header">
                        <h3>Results ({results.length})</h3>
                        <button className="download-btn" onClick={handleDownloadCSV}>
                            Download CSV
                        </button>
                    </div>

                    <div className="table-wrapper">
                        <table className="premium-table">
                            <thead>
                                <tr>
                                    <th>Ticker</th>
                                    <th>Company</th>
                                    <th>Price</th>
                                    <th>P/E</th>
                                    <th>P/B</th>
                                    <th>ROE</th>
                                    <th>Debt/Eq</th>
                                    <th>Sector</th>
                                </tr>
                            </thead>
                            <tbody>
                                {results.map((row, index) => (
                                    <tr key={index}>
                                        <td className="ticker-cell">{row.Ticker}</td>
                                        <td className="company-cell">{row.Company}</td>
                                        <td className="number-cell">{formatValue('Price', row.Price)}</td>
                                        <td className="number-cell">{formatValue('P/E', row['P/E'])}</td>
                                        <td className="number-cell">{formatValue('P/B', row['P/B'])}</td>
                                        <td className="number-cell">{formatValue('ROE', row['ROE'])}</td>
                                        <td className="number-cell">{formatValue('Debt/Equity', row['Debt/Equity'])}</td>
                                        <td className="sector-cell">{row.Sector}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </div>
            )}

            {results.length === 0 && !loading && !error && (
                <div className="empty-state">
                    <p>Select criteria and hit Search to find stocks.</p>
                </div>
            )}
        </div>
    );
};

export default StockScreener;
