import { useTranslation } from 'react-i18next';
import './App.css';

const Selector = ({ activeView, onViewChange, isOpen, onToggle }) => {
    const { t } = useTranslation();

    return (
        <>
            <button
                className={`menu-toggle ${isOpen ? 'hidden' : ''}`}
                type="button"
                onClick={onToggle}
                aria-label="Toggle menu"
                aria-expanded={isOpen}
                aria-controls="app-sidebar"
            >
                <span className="hamburger">☰</span>
            </button>
            <div className={`sidebar ${isOpen ? 'open' : ''}`} id="app-sidebar">
                <div className="sidebar-header">
                    <h2>Antifier</h2>
                    <button className="close-button" type="button" onClick={onToggle} aria-label={t('common.close')}>×</button>
                </div>
                <nav className="sidebar-nav">
                    <button
                        className={`nav-item ${activeView === 'stock' ? 'active' : ''}`}
                        type="button"
                        aria-current={activeView === 'stock' ? 'page' : undefined}
                        onClick={() => {
                            onViewChange('stock');
                            onToggle();
                        }}
                    >
                        <img src="/stock-data-transparent.png" className="icon" alt="Stock" />
                        {t('navigation.stock')}
                    </button>
                    <button
                        className={`nav-item ${activeView === 'hedge' ? 'active' : ''}`}
                        type="button"
                        aria-current={activeView === 'hedge' ? 'page' : undefined}
                        onClick={() => {
                            onViewChange('hedge');
                            onToggle();
                        }}
                    >
                        <img src="/hedge-transparent.png" className="icon" alt="Hedge" />
                        {t('navigation.hedge')}
                    </button>
                    <button
                        className={`nav-item ${activeView === 'financial' ? 'active' : ''}`}
                        type="button"
                        aria-current={activeView === 'financial' ? 'page' : undefined}
                        onClick={() => {
                            onViewChange('financial');
                            onToggle();
                        }}
                    >
                        <img src="/finincial-statement-transparent.png" className="icon" alt="Financial" />
                        {t('navigation.financial')}
                    </button>
                    <button
                        className={`nav-item ${activeView === 'optimizer' ? 'active' : ''}`}
                        type="button"
                        aria-current={activeView === 'optimizer' ? 'page' : undefined}
                        onClick={() => {
                            onViewChange('optimizer');
                            onToggle();
                        }}
                    >
                        <img src="/portfolio-transparent.png" className="icon" alt="Optimizer" />
                        {t('navigation.optimizer')}
                    </button>
                    <button
                        className={`nav-item ${activeView === 'benchmark' ? 'active' : ''}`}
                        type="button"
                        aria-current={activeView === 'benchmark' ? 'page' : undefined}
                        onClick={() => {
                            onViewChange('benchmark');
                            onToggle();
                        }}
                    >
                        <img src="/benchmark-transparent.png" className="icon" alt="Benchmark" />
                        {t('navigation.benchmark')}
                    </button>
                    <button
                        className={`nav-item ${activeView === 'manager' ? 'active' : ''}`}
                        type="button"
                        aria-current={activeView === 'manager' ? 'page' : undefined}
                        onClick={() => {
                            onViewChange('manager');
                            onToggle();
                        }}
                    >
                        <img src="/portfolio-manager-transparent.png" className="icon" alt="Manager" />
                        {t('navigation.manager')}
                    </button>
                </nav>
            </div>
        </>
    );
};

export default Selector;
