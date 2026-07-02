import { useState, useCallback, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { apiUrl } from './apiClient.js';
import { ScreenerSkeleton } from './SkeletonScreens.jsx';
import './App.css';

// Define available metrics
// Matches backend keys
const METRICS = [
    { value: 'Financial Score', labelKey: 'stockScreener.metrics.financialScore' },
    { value: 'P/E', labelKey: 'stockScreener.metrics.pe' },
    { value: 'Forward P/E', labelKey: 'stockScreener.metrics.forwardPe' },
    { value: 'P/B', labelKey: 'stockScreener.metrics.pb' },
    { value: 'Price/Sales', labelKey: 'stockScreener.metrics.priceSales' },
    { value: 'PEG', labelKey: 'stockScreener.metrics.peg' },
    { value: 'Debt/Equity', labelKey: 'stockScreener.metrics.debtEquity' },
    { value: 'ROE', labelKey: 'stockScreener.metrics.roe' },
    { value: 'ROA', labelKey: 'stockScreener.metrics.roa' },
    { value: 'Profit Margin', labelKey: 'stockScreener.metrics.profitMargin' },
    { value: 'Market Cap', labelKey: 'stockScreener.metrics.marketCap' },
    { value: 'Price', labelKey: 'stockScreener.metrics.currentPrice' },
];

const OPERATORS = [
    { value: 'Under', labelKey: 'stockScreener.operators.under' },
    { value: 'Over', labelKey: 'stockScreener.operators.over' },
    { value: 'Equals', labelKey: 'stockScreener.operators.equals' },
];

const DECISION_LABEL_KEYS = {
    'STRONG BUY': 'strong_buy',
    BUY: 'buy',
    HOLD: 'hold',
    REDUCE: 'reduce',
    SELL: 'sell',
    'INSUFFICIENT DATA': 'insufficient_data',
};

const StockScreener = () => {
    const { t } = useTranslation();
    const [tickerGroup, setTickerGroup] = useState('S&P 500');
    const [filters, setFilters] = useState([
        { metric: 'Financial Score', operator: 'Over', value: '65' },
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
        setFilters([...filters, { metric: 'Financial Score', operator: 'Over', value: '' }]);
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
            setUploadError(t('stockScreener.csvOnly'));
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
                setUploadError(t('stockScreener.noValidTickers'));
                setCustomTickers([]);
            } else {
                setCustomTickers(tickers);
            }
        };
        reader.onerror = () => {
            setUploadError(t('stockScreener.readError'));
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

        if (tickerGroup === 'Custom' && customTickers.length === 0) {
            setError(t('stockScreener.uploadCsvRequired'));
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
                throw new Error(errData.error || t('stockScreener.networkError'));
            }

            const data = await response.json();
            setResults(data);
        } catch (err) {
            setError(err.message || t('stockScreener.fetchError'));
            if (import.meta.env.DEV) {
                console.error(err);
            }
        } finally {
            setLoading(false);
        }
    }, [filters, tickerGroup, customTickers, t]);

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
        if (key === 'Financial Score') {
            return `${Math.round(val)}/100`;
        }
        if (key === 'Score Confidence') {
            return `${Math.round(val)}%`;
        }
        if (['ROE', 'ROA', 'Profit Margin'].includes(key)) {
            return `${(val * 100).toFixed(2)}%`;
        }
        return val;
    };

    const formatSignal = (label) => {
        if (!label) return '-';
        const labelKey = DECISION_LABEL_KEYS[label];
        return labelKey ? t(`financial.decision_labels.${labelKey}`, label) : label;
    };

    return (
        <div className="stock-screener-container">
            <div className="page-title-block">
                <span className="page-kicker">{t('stockScreener.kicker')}</span>
                <h1 className="page-header">{t('stockScreener.stock_screener')}</h1>
            </div>

            <div className="screener-controls-card">
                <div className="control-header">
                    <h3>{t('stockScreener.screeningCriteria')}</h3>
                    <div className="universe-selector">
                        <label>{t('stockScreener.universe')}</label>
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
                                <option value="Custom">{t('stockScreener.customCsv')}</option>
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
                                {METRICS.map(m => <option key={m.value} value={m.value}>{t(m.labelKey)}</option>)}
                            </select>
                            <select
                                className="premium-select operator-select"
                                value={filter.operator}
                                onChange={(e) => handleFilterChange(index, 'operator', e.target.value)}
                            >
                                {OPERATORS.map(o => <option key={o.value} value={o.value}>{t(o.labelKey)}</option>)}
                            </select>
                            <input
                                type="text"
                                className="premium-input value-input"
                                value={filter.value}
                                onChange={(e) => handleFilterChange(index, 'value', e.target.value)}
                                placeholder={t('stockScreener.valuePlaceholder')}
                            />
                            <button
                                className="remove-filter-btn"
                                onClick={() => handleRemoveFilter(index)}
                                aria-label={t('stockScreener.removeFilter')}
                            >
                                ×
                            </button>
                        </div>
                    ))}
                </div>

                <div className="action-row">
                    <button className="secondary-btn" onClick={handleAddFilter}>
                        {t('stockScreener.add_filter')}
                    </button>
                    <button className="primary-btn search-btn" onClick={handleSearch} disabled={loading}>
                        {loading ? t('stockScreener.screening') : t('stockScreener.searchStocks')}
                    </button>
                </div>
            </div>

            {showUploadModal && (
                <div className="optimizer-modal-overlay" onClick={handleCloseUploadModal}>
                    <div className="optimizer-modal-content" onClick={e => e.stopPropagation()}>
                        <div className="optimizer-modal-header">
                            <h3 className="optimizer-modal-title">{t('optimizer.uploadCustomTickers')}</h3>
                            <button type="button" className="optimizer-modal-close" onClick={handleCloseUploadModal} aria-label={t('common.close')}>×</button>
                        </div>
                        <div className="optimizer-modal-body">
                            <p style={{ fontSize: '0.85rem', color: 'var(--color-text-muted)', marginBottom: 'var(--spacing-md)' }}>
                                {t('optimizer.customTickersHelp')}
                            </p>
                            <button
                                type="button"
                                className="secondary-btn"
                                onClick={() => fileInputRef.current?.click()}
                                style={{ width: '100%', marginBottom: 'var(--spacing-md)' }}
                            >
                                {uploadFileName ? t('optimizer.changeFile') : t('optimizer.chooseCsvFile')}
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
                                    <strong>{uploadFileName}</strong> - {t('optimizer.tickersLoaded', { count: customTickers.length })}
                                    <ul className="optimizer-weights-list" style={{ marginTop: 'var(--spacing-sm)', maxHeight: '150px' }}>
                                        {customTickers.map(t => <li key={t}><span>{t}</span></li>)}
                                    </ul>
                                </div>
                            )}
                        </div>
                        <div className="optimizer-modal-footer">
                            {customTickers.length > 0 && (
                                <button type="button" className="secondary-btn" onClick={handleClearUpload}>
                                    {t('common.clear')}
                                </button>
                            )}
                            <button type="button" className="primary-btn" onClick={handleCloseUploadModal}>
                                {t('common.done')}
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {error && <div className="error-banner">{error}</div>}

            {loading && <ScreenerSkeleton />}

            {!loading && results.length > 0 && (
                <div className="results-section fade-in">
                    <div className="results-header">
                        <h3>{t('stockScreener.resultsWithCount', { count: results.length })}</h3>
                        <button className="download-btn" onClick={handleDownloadCSV}>
                            {t('stockScreener.download_csv')}
                        </button>
                    </div>

                    <div className="table-wrapper">
                        <table className="premium-table">
                            <thead>
                                <tr>
                                    <th>{t('stockScreener.table.ticker')}</th>
                                    <th>{t('stockScreener.table.company')}</th>
                                    <th>{t('stockScreener.table.score')}</th>
                                    <th>{t('stockScreener.table.signal')}</th>
                                    <th>{t('stockScreener.table.confidence')}</th>
                                    <th>{t('stockScreener.table.price')}</th>
                                    <th>{t('stockScreener.table.pe')}</th>
                                    <th>{t('stockScreener.table.pb')}</th>
                                    <th>{t('stockScreener.table.roe')}</th>
                                    <th>{t('stockScreener.table.debtEquity')}</th>
                                    <th>{t('stockScreener.table.sector')}</th>
                                </tr>
                            </thead>
                            <tbody>
                                {results.map((row, index) => (
                                    <tr key={index}>
                                        <td className="ticker-cell">{row.Ticker}</td>
                                        <td className="company-cell">{row.Company}</td>
                                        <td className="number-cell">{formatValue('Financial Score', row['Financial Score'])}</td>
                                        <td>{formatSignal(row['Financial Signal'])}</td>
                                        <td className="number-cell">{formatValue('Score Confidence', row['Score Confidence'])}</td>
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
                    <p>{t('stockScreener.emptyState')}</p>
                </div>
            )}
        </div>
    );
};

export default StockScreener;
