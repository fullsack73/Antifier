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
        <div className="page-container">
            <h2 className="page-header">{t('hedge.title')}</h2>

            <form onSubmit={handleSubmit} className="controls-container">
                <div className="ticker-input-container">
                    <div className="ticker-input-group">
                        <label htmlFor="ticker1">{t('hedge.label1')}</label>
                        <input
                            type="text"
                            id="ticker1"
                            value={ticker1}
                            onChange={(e) => setTicker1(e.target.value.toUpperCase())}
                            placeholder="e.g., AAPL"
                        />
                    </div>
                </div>

                <div className="date-input-container">
                    <div className="date-input-group">
                        <label htmlFor="startDate">{t('date.start')}</label>
                        <input
                            type="date"
                            id="startDate"
                            value={startDate}
                            onChange={(e) => setStartDate(e.target.value)}
                        />
                    </div>
                    <div className="date-input-group">
                        <label htmlFor="endDate">{t('date.end')}</label>
                        <input
                            type="date"
                            id="endDate"
                            value={endDate}
                            onChange={(e) => setEndDate(e.target.value)}
                        />
                    </div>
                </div>

                <div className="ticker-input-container">
                    <div className="ticker-input-group">
                        <label htmlFor="ticker2">{t('hedge.label2')}</label>
                        <input
                            type="text"
                            id="ticker2"
                            value={ticker2}
                            onChange={(e) => setTicker2(e.target.value.toUpperCase())}
                            placeholder="e.g., MSFT"
                        />
                    </div>
                </div>
                <button type="submit" onClick={handleSubmit} disabled={loading} className="ticker-search-btn" style={{ width: '100%', marginTop: '1rem' }}>
                    {loading ? t('common.loading') : t('common.submit')}
                </button>
            </form>

            {error && <div className="error-message">{error}</div>}

            {hedgeData && (
                <div style={{ marginTop: "2rem" }}>
                    <h2>{t('hedge.results')}</h2>
                    <div className="grid-auto">

                        <div className="stat-card">
                            <h4>{t('hedge.companies')}</h4>
                            <p className="value" style={{ fontSize: "1.2rem" }}>{hedgeData.company1} ({hedgeData.ticker1})</p>
                            <p className="value" style={{ fontSize: "1.2rem" }}>{hedgeData.company2} ({hedgeData.ticker2})</p>
                        </div>

                        <div className="stat-card">
                            <h4>{t('hedge.relationship')}</h4>
                            <p className={`value ${hedgeData.is_hedge ? 'text-accent' : 'text-danger'}`}>
                                {hedgeData.is_hedge ? 'Yes' : 'No'}
                            </p>
                            <p>{t('hedge.strength')}: {hedgeData.strength}</p>
                        </div>

                        <div className="stat-card">
                            <h4>{t('hedge.statisticalAnalysis')}</h4>
                            <p>{t('hedge.correlation')}: <span className="text-accent">{hedgeData.correlation.toFixed(3)}</span></p>
                            <p>{t('hedge.pValue')}: <span className="text-accent">{hedgeData.p_value.toFixed(4)}</span></p>
                        </div>

                        <div className="stat-card">
                            <h4>{t('hedge.analysisPeriod')}</h4>
                            <p style={{ fontSize: "0.9rem" }}>{t('date.start')}: {hedgeData.period.start}</p>
                            <p style={{ fontSize: "0.9rem" }}>{t('date.end')}: {hedgeData.period.end}</p>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

export default HedgeAnalysis;
