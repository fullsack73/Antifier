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
    <div className="input-group">
      <label htmlFor="model-select" style={{ display: 'block', marginBottom: '5px' }}>{t('model.select') || 'Select AI Model'}</label>
      <select 
        id="model-select" 
        value={model} 
        onChange={handleChange}
        className="model-select"
        style={{ width: '100%', padding: '8px', borderRadius: '4px', border: '1px solid #444', backgroundColor: '#222', color: '#fff' }}
      >
        <option value="LSTM">LSTM (Neural Network)</option>
        <option value="LightGBM">LightGBM (Gradient Boosting)</option>
        <option value="ARIMA">ARIMA (Time Series)</option>
      </select>
    </div>
  );
}

export default ModelSelector;
