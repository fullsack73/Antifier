import { useCallback, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import StockScreener from './StockScreener';
import { apiUrl } from './apiClient.js';
import { MetricCardsSkeleton } from './SkeletonScreens.jsx';
import './App.css';

const DECISION_LABEL_KEYS = {
    'STRONG BUY': 'strong_buy',
    BUY: 'buy',
    HOLD: 'hold',
    REDUCE: 'reduce',
    SELL: 'sell',
    'INSUFFICIENT DATA': 'insufficient_data',
};

const CATEGORY_ORDER = ['valuation', 'profitability', 'growth', 'stability', 'risk'];
const STATEMENT_TYPES = ['income', 'balance', 'cash'];
const FREQUENCIES = ['annual', 'quarterly'];

const FinancialStatement = () => {
    const { t } = useTranslation();
    const [ticker, setTicker] = useState('AAPL');
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);
    const [showStatements, setShowStatements] = useState(false);
    const [statementType, setStatementType] = useState('income');
    const [frequency, setFrequency] = useState('annual');

    const fetchFinancialData = useCallback(async () => {
        if (!ticker.trim()) return;
        setLoading(true);
        setError(null);

        try {
            const response = await fetch(apiUrl('/api/financial-statement', { ticker }));
            const result = await response.json();

            if (!response.ok) {
                throw new Error(result.error || `HTTP error! status: ${response.status}`);
            }

            if (result.error) {
                throw new Error(result.error);
            }

            setData(result);
        } catch (err) {
            if (import.meta.env.DEV) {
                console.error('Fetch error:', err);
            }
            setError(err.message);
            setData(null);
        } finally {
            setLoading(false);
        }
    }, [ticker]);

    const groupedMetrics = useMemo(() => {
        const groups = {};
        (data?.metrics || []).forEach((metric) => {
            const category = metric.category || 'other';
            if (!groups[category]) groups[category] = [];
            groups[category].push(metric);
        });
        return groups;
    }, [data]);

    const handleSearch = (e) => {
        e.preventDefault();
        fetchFinancialData();
    };

    const formatNumber = (val) => {
        if (val === null || val === undefined) return '-';
        if (typeof val === 'number') {
            return new Intl.NumberFormat('en-US', {
                maximumFractionDigits: 0,
                notation: Math.abs(val) > 1000000 ? 'compact' : 'standard',
            }).format(val);
        }
        return val;
    };

    const decisionKey = (label) => DECISION_LABEL_KEYS[label] || 'insufficient_data';

    const renderDecision = () => {
        const decision = data?.decision;
        if (!decision) return null;

        const labelKey = decisionKey(decision.label);
        const label = t(`financial.decision_labels.${labelKey}`, decision.label);
        const scoreText = decision.score === null || decision.score === undefined
            ? '-'
            : `${decision.score}/${decision.max_score || 100}`;

        return (
            <section className={`financial-decision-panel decision-${labelKey}`}>
                <div className="financial-company-summary">
                    <span className="financial-dashboard-kicker">
                        {data.company?.sector || t('financial.not_available')} · {data.company?.industry || t('financial.not_available')}
                    </span>
                    <h3>{data.company?.name || data.longName || data.ticker} ({data.ticker})</h3>
                    <div className="financial-company-meta">
                        <span>{t('financial.market_cap')}: {data.company?.market_cap_display || t('financial.not_available')}</span>
                        <span>{t('financial.currency')}: {data.company?.currency || t('financial.not_available')}</span>
                    </div>
                </div>
                <div className="financial-score-summary">
                    <span className="financial-decision-label">{label}</span>
                    <strong>{scoreText}</strong>
                    <span>
                        {t('financial.confidence', {
                            confidence: decision.confidence ?? 0,
                            available: decision.available_metrics ?? 0,
                            total: decision.total_metrics ?? 0,
                        })}
                    </span>
                </div>
            </section>
        );
    };

    const renderComparison = (metric) => {
        const comparison = metric.comparison || {};
        if (comparison.status === 'available') {
            const position = t(`financial.benchmark_position.${comparison.position}`, comparison.position);
            return t('financial.benchmark_available', {
                benchmark: comparison.benchmark_name || comparison.industry || t('financial.not_available'),
                average: comparison.industry_average_display || '-',
                position,
                difference: comparison.relative_difference_display || '-',
            });
        }

        return t('financial.benchmark_unavailable', {
            industry: comparison.industry || data?.company?.industry || t('financial.not_available'),
        });
    };

    const renderMetricCard = (metric) => {
        const metricLabel = t(`financial.metric_labels.${metric.key}`, metric.label);
        const description = t(`financial.metric_descriptions.${metric.key}`, '');
        const signal = t(`financial.signal_descriptions.${metric.signal}`, metric.signal);
        const category = t(`financial.metric_categories.${metric.category}`, metric.category);
        const score = metric.score === null || metric.score === undefined ? '-' : metric.score;

        return (
            <article className={`financial-insight-card signal-${metric.signal}`} key={metric.key}>
                <div className="financial-insight-card-header">
                    <span className="financial-metric-category">{category}</span>
                    <span className="financial-metric-score">{score}/100</span>
                </div>
                <h4>{metricLabel}</h4>
                <p className="financial-metric-value">{metric.display_value || t('financial.not_available')}</p>
                <p className="financial-metric-description">{description}</p>
                <p className="financial-metric-signal">{signal}</p>
                <p className="financial-metric-comparison">{renderComparison(metric)}</p>
                <span className="financial-threshold">{t('financial.rule')}: {metric.threshold}</span>
            </article>
        );
    };

    const renderDashboard = () => {
        if (!data) return null;

        return (
            <div className="financial-dashboard animate-fade-in">
                {renderDecision()}

                <div className="financial-dashboard-actions">
                    <p>{t('financial.analysis_note')}</p>
                    <button
                        type="button"
                        className="financial-secondary-button"
                        onClick={() => setShowStatements(true)}
                    >
                        {t('financial.view_full_statements')}
                    </button>
                </div>

                {CATEGORY_ORDER.map((category) => {
                    const metrics = groupedMetrics[category] || [];
                    if (!metrics.length) return null;

                    return (
                        <section className="financial-metric-section" key={category}>
                            <h3>{t(`financial.metric_categories.${category}`, category)}</h3>
                            <div className="financial-insights-grid">
                                {metrics.map(renderMetricCard)}
                            </div>
                        </section>
                    );
                })}
            </div>
        );
    };

    const renderTable = (tableData, tableError) => {
        if (tableError && !tableData) {
            return <div className="empty-state"><p>{tableError}</p></div>;
        }

        if (!tableData || !tableData.dates) {
            return <div className="empty-state"><p>{t('financial.no_statement_data')}</p></div>;
        }

        return (
            <div className="financial-table-container animate-fade-in">
                <table className="financial-table">
                    <thead>
                        <tr>
                            <th>{t('financial.breakdown')}</th>
                            {tableData.dates.map((date) => (
                                <th key={date}>{date}</th>
                            ))}
                        </tr>
                    </thead>
                    <tbody>
                        {tableData.breakdown.map((row) => (
                            <tr key={row.row_label}>
                                <td>{row.row_label}</td>
                                {row.values.map((val, index) => (
                                    <td key={`${row.row_label}-${index}`}>{formatNumber(val)}</td>
                                ))}
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        );
    };

    const renderStatementsModal = () => {
        if (!showStatements || !data) return null;

        const tableData = data.statements?.[frequency]?.[statementType];
        const tableError = data.statement_errors?.[frequency]?.[statementType];

        return (
            <div className="optimizer-modal-overlay" onClick={() => setShowStatements(false)}>
                <div
                    className="optimizer-modal-content financial-statement-modal"
                    onClick={(event) => event.stopPropagation()}
                    role="dialog"
                    aria-modal="true"
                    aria-labelledby="financial-statement-modal-title"
                >
                    <div className="optimizer-modal-header">
                        <h3 className="optimizer-modal-title" id="financial-statement-modal-title">
                            {t('financial.full_statements_title')}
                        </h3>
                        <button
                            type="button"
                            className="optimizer-modal-close"
                            onClick={() => setShowStatements(false)}
                            aria-label={t('common.close')}
                        >
                            ×
                        </button>
                    </div>
                    <div className="optimizer-modal-body financial-statement-modal-body">
                        <div className="financial-segment-row" role="tablist" aria-label={t('financial.full_statements_title')}>
                            {STATEMENT_TYPES.map((type) => (
                                <button
                                    key={type}
                                    type="button"
                                    className={`financial-segment-button${statementType === type ? ' is-active' : ''}`}
                                    onClick={() => setStatementType(type)}
                                    aria-pressed={statementType === type}
                                >
                                    {t(`financial.${type}`)}
                                </button>
                            ))}
                        </div>
                        <div className="financial-segment-row financial-frequency-row" aria-label={t('financial.frequency')}>
                            {FREQUENCIES.map((item) => (
                                <button
                                    key={item}
                                    type="button"
                                    className={`financial-segment-button${frequency === item ? ' is-active' : ''}`}
                                    onClick={() => setFrequency(item)}
                                    aria-pressed={frequency === item}
                                >
                                    {t(`financial.${item}`)}
                                </button>
                            ))}
                        </div>
                        {renderTable(tableData, tableError)}
                    </div>
                    <div className="optimizer-modal-footer">
                        <button
                            type="button"
                            className="financial-secondary-button"
                            onClick={() => setShowStatements(false)}
                        >
                            {t('common.close')}
                        </button>
                    </div>
                </div>
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
                    <button type="submit" className="ticker-search-btn" disabled={loading}>
                        {loading ? t('common.loading') : t('financial.fetch_data')}
                    </button>
                </form>
            </div>

            {error && <div className="error-message">{t('common.error')}: {error}</div>}

            <div className="financial-content">
                {loading ? (
                    <MetricCardsSkeleton cards={8} label={t('financial.loading_dashboard')} />
                ) : renderDashboard()}

                {!loading && !error && !data && (
                    <div className="empty-state">
                        <p>{t('financial.empty_dashboard')}</p>
                    </div>
                )}
            </div>

            {renderStatementsModal()}

            <div className="financial-screener-section">
                <StockScreener />
            </div>
        </div>
    );
};

export default FinancialStatement;
