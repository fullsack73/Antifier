import React from 'react';
import { useTranslation } from 'react-i18next';
import './App.css';

const Selector = ({ activeView, onViewChange, isOpen, onToggle }) => {
    const { t } = useTranslation();

    return (
        <>
            <button
                className={`menu-toggle ${isOpen ? 'hidden' : ''}`}
                onClick={onToggle}
                aria-label="Toggle menu"
            >
                <span className="hamburger">☰</span>
            </button>
            <div className={`sidebar ${isOpen ? 'open' : ''}`}>
                <div className="sidebar-header">
                    <h2>Antifier</h2>
                    <button className="close-button" onClick={onToggle}>×</button>
                </div>
                <nav className="sidebar-nav">
                    <button
                        className={`nav-item ${activeView === 'stock' ? 'active' : ''}`}
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
                        onClick={() => {
                            onViewChange('benchmark');
                            onToggle();
                        }}
                    >
                        <img src="/benchmark-transparent.png" className="icon" alt="Benchmark" />
                        {t('navigation.benchmark')}
                    </button>
                </nav>
            </div>
        </>
    );
};

export default Selector;