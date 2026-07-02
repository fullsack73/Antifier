import { useState } from 'react';
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
          <option value="LSTM">{t('model.lstm', 'LSTM (Neural Network)')}</option>
          <option value="LightGBM">{t('model.lightgbm', 'LightGBM (Gradient Boosting)')}</option>
          <option value="ARIMA">{t('model.arima', 'ARIMA (Time Series)')}</option>
          <option value="ARIMA_TRANSFORMER">{t('model.arimaTransformer', 'ARIMA + Transformer')}</option>
          <option value="TRANSFORMER">{t('model.transformer', 'Transformer')}</option>
        </select>
      </div>
    </div>
  );
}

export default ModelSelector;
