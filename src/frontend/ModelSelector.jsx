import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import './App.css'; 

function ModelSelector({ onModelChange, initialModel = 'LSTM' }) {
  const [model, setModel] = useState(initialModel);
  const { t } = useTranslation();

  const handleChange = (e) => {
    const newModel = e.target.value;
    setModel(newModel);
    if (onModelChange) {
      onModelChange(newModel);
    }
  };

  return (
    <div className="ticker-input-container">
      <div className="ticker-input-group">
        <label htmlFor="model-select">{t('model.select')}</label>
        <select 
          id="model-select" 
          value={model} 
          onChange={handleChange}
        >
          <option value="LSTM">LSTM (Neural Network)</option>
          <option value="LightGBM">LightGBM (Gradient Boosting)</option>
          <option value="ARIMA">ARIMA (Time Series)</option>
          <option value="ARIMA_TRANSFORMER">ARIMA + Transformer</option>
          <option value="TRANSFORMER">Transformer</option>
        </select>
      </div>
    </div>
  );
}

export default ModelSelector;
