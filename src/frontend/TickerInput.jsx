import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import './App.css';

function TickerInput({ onTickerChange, initialTicker = '' }) {
  const [ticker, setTicker] = useState(initialTicker);
  const { t } = useTranslation();
  const updateTimeoutRef = useRef(null);

  useEffect(() => () => clearTimeout(updateTimeoutRef.current), []);

  const scheduleTickerChange = (newTicker) => {
    clearTimeout(updateTimeoutRef.current);
    updateTimeoutRef.current = setTimeout(() => {
      if (newTicker && onTickerChange) {
        onTickerChange(newTicker);
      }
    }, 300);
  };

  const handleInputChange = (e) => {
    const newTicker = e.target.value.trim().toUpperCase();
    setTicker(newTicker);
    
    if (newTicker && newTicker.length >= 1) {
      scheduleTickerChange(newTicker);
    }
  };

  return (
    <div className="ticker-input-container">
      <div className="ticker-input-group">
        <label htmlFor="ticker">{t('ticker.label')}</label>
        <input
          type="text"
          id="ticker"
          value={ticker}
          onChange={handleInputChange}
          placeholder={t('ticker.placeholder')}
          title="Charts will auto-update as you type"
          maxLength="10"
        />
      </div>
    </div>
  );
}

export default TickerInput;
