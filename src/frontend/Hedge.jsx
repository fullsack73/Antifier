import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import './App.css';

const HedgeAnalysis = () => {
    const { t } = useTranslation();
    const [ticker1, setTicker1] = useState('');
    const [ticker2, setTicker2] = useState('');
    const [startDate, setStartDate] = useState('');
    const [endDate, setEndDate] = useState('');
    const [hedgeData, setHedgeData] = useState(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);

    const fetchHedgeData = async () => {
        if (!ticker1 || !ticker2) {
            setError('Please enter both tickers');
            return;
        }

        setLoading(true);
        setError(null);

        try {
            const url = new URL('/analyze-hedge', 'http://127.0.0.1:5000');
            url.searchParams.append('ticker1', ticker1.toUpperCase());
            url.searchParams.append('ticker2', ticker2.toUpperCase());
            if (startDate) url.searchParams.append('start_date', startDate);
            if (endDate) url.searchParams.append('end_date', endDate);

            const response = await fetch(url);
            const data = await response.json();

            if (data.error) {
                setError(data.error);
                return;
            }

            setHedgeData(data);
        } catch (err) {
            setError('Failed to fetch hedge analysis data');
            console.error('Error fetching hedge data:', err);
        } finally {
            setLoading(false);
        }
    };

    const handleSubmit = (e) => {
        e.preventDefault();
        fetchHedgeData();
    };

    return (
        <div className="hedge-analysis">
            <h2 className="page-header">{t('hedge.title')}</h2>

            <form onSubmit={handleSubmit} className="hedge-form">
                <div className="hedge-form-grid">
                    <div className="form-group">
                        <label htmlFor="ticker1">{t('hedge.label1')}:</label>
                        <input
                            type="text"
                            id="ticker1"
                            value={ticker1}
                            onChange={(e) => setTicker1(e.target.value.toUpperCase())}
                            placeholder="e.g., AAPL"
                            className="hedge-input"
                        />
                    </div>

                    <div className="form-group">
                        <label htmlFor="ticker2">{t('hedge.label2')}:</label>
                        <input
                            type="text"
                            id="ticker2"
                            value={ticker2}
                            onChange={(e) => setTicker2(e.target.value.toUpperCase())}
                            placeholder="e.g., MSFT"
                            className="hedge-input"
                        />
                    </div>

                    <div className="form-group">
                        <label htmlFor="startDate">{t('date.start')}:</label>
                        <input
                            type="date"
                            id="startDate"
                            value={startDate}
                            onChange={(e) => setStartDate(e.target.value)}
                            className="hedge-input"
                        />
                    </div>

                    <div className="form-group">
                        <label htmlFor="endDate">{t('date.end')}:</label>
                        <input
                            type="date"
                            id="endDate"
                            value={endDate}
                            onChange={(e) => setEndDate(e.target.value)}
                            className="hedge-input"
                        />
                    </div>
                </div>

                <button type="submit" disabled={loading} className="hedge-submit-button">
                    {loading ? t('common.loading') : t('common.submit')}
                </button>
            </form>

            {error && <div className="error-message">{error}</div>}

            {hedgeData && (
                <div className="hedge-results">
                    <h3>{t('hedge.results')}</h3>
                    <div className="hedge-results-grid">

                        <div className="hedge-result-card">
                            <h4>{t('hedge.companies')}</h4>
                            <p>{hedgeData.company1} ({hedgeData.ticker1})</p>
                            <p>{hedgeData.company2} ({hedgeData.ticker2})</p>
                        </div>

                        <div className="hedge-result-card">
                            <h4>{t('hedge.relationship')}</h4>
                            <p className={`hedge-value-highlight ${hedgeData.is_hedge ? 'hedge-positive' : 'hedge-negative'}`}>
                                {hedgeData.is_hedge ? 'Yes' : 'No'}
                            </p>
                            <p>{t('hedge.strength')}: {hedgeData.strength}</p>
                        </div>

                        <div className="hedge-result-card">
                            <h4>{t('hedge.statisticalAnalysis')}</h4>
                            <p>{t('hedge.correlation')}: <span style={{ color: 'var(--color-primary-light)' }}>{hedgeData.correlation.toFixed(3)}</span></p>
                            <p>{t('hedge.pValue')}: <span style={{ color: 'var(--color-primary-light)' }}>{hedgeData.p_value.toFixed(4)}</span></p>
                        </div>

                        <div className="hedge-result-card">
                            <h4>{t('hedge.analysisPeriod')}</h4>
                            <p>{t('date.start')}: {hedgeData.period.start}</p>
                            <p>{t('date.end')}: {hedgeData.period.end}</p>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

export default HedgeAnalysis;
