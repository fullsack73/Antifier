import React, { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import StockScreener from './StockScreener';
import './App.css'; // Ensure CSS is imported

const FinancialStatement = () => {
    const { t } = useTranslation();
    const [ticker, setTicker] = useState('AAPL');
    const [view, setView] = useState('summary'); // 'summary', 'income', 'balance', 'cash'
    const [frequency, setFrequency] = useState('annual'); // 'annual', 'quarterly'

    const [data, setData] = useState(null); // For summary/ratios
    const [statementData, setStatementData] = useState(null); // For tables
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);

    const [hoveredMetric, setHoveredMetric] = useState(null);

    const fetchFinancialData = async () => {
        if (!ticker) return;
        setLoading(true);
        setError(null);

        try {
            let url = `http://127.0.0.1:5000/financial-statement?ticker=${ticker}`;
            if (view !== 'summary') {
                url += `&type=${view}&frequency=${frequency}`;
            }

            const response = await fetch(url);
            const result = await response.json();

            if (!response.ok) {
                throw new Error(result.error || `HTTP error! status: ${response.status}`);
            }

            if (result.error) {
                throw new Error(result.error);
            }

            if (view === 'summary') {
                setData(result);
                setStatementData(null);
            } else {
                setStatementData(result);
                // Keep existing summary data if available, or fetch it? 
                // For now, let's just focus on the active view.
            }

        } catch (err) {
            console.error("Fetch error:", err);
            setError(err.message);
            if (view !== 'summary') setStatementData(null);
            else setData(null);
        } finally {
            setLoading(false);
        }
    };

    // Re-fetch when view or frequency changes, if we have a ticker and have already fetched once (optional auto-refresh logic)
    // For now, let's rely on the "Fetch" button for the initial load, and auto-fetch on view change if we already have data.
    // Actually, user expects tabs to switch views immediately.
    useEffect(() => {
        // Only auto-fetch if we aren't completely empty
        if ((data || statementData || error) && !loading) {
            fetchFinancialData();
        }
    }, [view, frequency]);

    const handleSearch = (e) => {
        e.preventDefault();
        fetchFinancialData();
    };

    const formatNumber = (val) => {
        if (val === null || val === undefined) return '-';
        if (typeof val === 'number') {
            return new Intl.NumberFormat('en-US', {
                maximumFractionDigits: 0,
                notation: Math.abs(val) > 1000000 ? 'compact' : 'standard'
            }).format(val);
        }
        return val;
    };

    const renderMetricCard = (title, value, tooltip) => (
        <div
            className="metric-card"
            onMouseEnter={() => setHoveredMetric(title)}
            onMouseLeave={() => setHoveredMetric(null)}
        >
            <h4>{title}</h4>
            <p>{value}</p>
            {tooltip && (
                <div className={`metric-tooltip ${hoveredMetric === title ? 'visible' : ''}`}>
                    {tooltip}
                </div>
            )}
        </div>
    );

    const renderSummary = () => {
        if (!data) return null;
        return (
            <div className="metrics-container animate-fade-in">
                <div className="text-center mb-8">
                    <h2 className="text-2xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-blue-400 to-teal-400">
                        {data.longName} ({data.ticker})
                    </h2>
                </div>
                <div className="metrics-grid">
                    {renderMetricCard(t('financial.per'), data.per, t('financial.per_tooltip'))}
                    {renderMetricCard(t('financial.pbr'), data.pbr, t('financial.pbr_tooltip'))}
                    {renderMetricCard(t('financial.psr'), data.psr, t('financial.psr_tooltip'))}
                    {renderMetricCard(t('financial.debt_ratio'), data.debt_ratio, t('financial.debt_ratio_tooltip'))}
                    {renderMetricCard(t('financial.liquidity_ratio'), data.liquidity_ratio, t('financial.liquidity_ratio_tooltip'))}
                </div>
            </div>
        );
    };

    const renderTable = () => {
        if (!statementData || !statementData.dates) return null;

        return (
            <div className="financial-table-container animate-fade-in">
                <table className="financial-table">
                    <thead>
                        <tr>
                            <th>Breakdown</th>
                            {statementData.dates.map((date, i) => (
                                <th key={i}>{date}</th>
                            ))}
                        </tr>
                    </thead>
                    <tbody>
                        {statementData.breakdown.map((row, i) => (
                            <tr key={i}>
                                <td>{row.row_label}</td>
                                {row.values.map((val, j) => (
                                    <td key={j}>{formatNumber(val)}</td>
                                ))}
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        );
    };

    return (
        <div className="financial-analysis-container">
            <div className="financial-header">
                <h2 className="page-header">{t('financial.title')}</h2>
            </div>

            <div className="financial-controls-wrapper">
                <form onSubmit={handleSearch} className="ticker-input-group">
                    <input
                        type="text"
                        value={ticker}
                        onChange={(e) => setTicker(e.target.value.toUpperCase())}
                        placeholder={t('ticker.placeholder')}
                    />
                    <div style={{ height: '10px' }}></div>
                    <button type="submit" className="ticker-search-btn" disabled={loading}>
                        {loading ? t('common.loading') : t('financial.fetch_data')}
                    </button>
                </form>
            </div>

            {error && <div className="error-message">{t('common.error')}: {error}</div>}

            <div className="financial-content">
                {view === 'summary' ? renderSummary() : renderTable()}

                {!loading && !error && !data && !statementData && (
                    <div className="empty-state">
                        <p>Enter a ticker symbol and click Fetch Data to begin analysis.</p>
                    </div>
                )}
            </div>

            <div className="mt-16 pt-8 border-t border-gray-800">
                <StockScreener />
            </div>
        </div>
    );
};

export default FinancialStatement;
