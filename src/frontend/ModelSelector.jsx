import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import './App.css'; 

const TRANSFORMER_MODELS = new Set(['ARIMA_TRANSFORMER', 'TRANSFORMER']);
const MINIMUM_TRAINING_OBSERVATIONS = 100;

const countWeekdays = (startDate, endDate) => {
  if (!startDate || !endDate) return null;

  const start = new Date(`${startDate}T00:00:00Z`);
  const end = new Date(`${endDate}T00:00:00Z`);
  if (!Number.isFinite(start.getTime()) || !Number.isFinite(end.getTime()) || start >= end) {
    return null;
  }

  let weekdays = 0;
  const cursor = new Date(start);
  while (cursor < end) {
    const day = cursor.getUTCDay();
    if (day !== 0 && day !== 6) weekdays += 1;
    cursor.setUTCDate(cursor.getUTCDate() + 1);
  }
  return weekdays;
};

function ModelSelector({
  onModelChange,
  initialModel = 'LSTM',
  startDate,
  endDate,
}) {
  const [model, setModel] = useState(initialModel);
  const { t } = useTranslation();

  const handleChange = (e) => {
    const newModel = e.target.value;
    setModel(newModel);
    if (onModelChange) {
      onModelChange(newModel);
    }
  };

  const usesTransformer = TRANSFORMER_MODELS.has(model);
  const estimatedWeekdays = countWeekdays(startDate, endDate);
  const hasInsufficientRange = usesTransformer
    && estimatedWeekdays !== null
    && estimatedWeekdays < MINIMUM_TRAINING_OBSERVATIONS;
  const warningTooltipId = 'model-training-warning-tooltip';
  const warningTooltip = t(
    'model.insufficientDataWarning',
    'This range contains fewer than 100 estimated market days. Transformer forecasting may use the lightweight fallback.',
  );

  return (
    <div className="ticker-input-container">
      <div className="ticker-input-group">
        <div className="model-selector-label-row">
          <label htmlFor="model-select">{t('model.select')}</label>
          {hasInsufficientRange && (
            <span
              className="model-warning-trigger"
              role="note"
              tabIndex="0"
              aria-label={t('model.trainingWarningLabel', 'Training data warning')}
              aria-describedby={warningTooltipId}
            >
              <span className="model-warning-text">{t('model.rangeNote', 'Range note')}</span>
              <span className="model-warning-tooltip" id={warningTooltipId} role="tooltip">
                {warningTooltip}
              </span>
            </span>
          )}
        </div>
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
