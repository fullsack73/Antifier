from native_threading import configure_native_threading

configure_native_threading()

import numpy as np
import logging
from scipy.stats import linregress
import warnings
import time
from sklearn.preprocessing import MinMaxScaler, StandardScaler

logger = logging.getLogger(__name__)


def _load_auto_arima():
    from pmdarima import auto_arima
    return auto_arima


def _load_tensorflow_keras():
    try:
        from tensorflow.keras.models import Sequential
        from tensorflow.keras.layers import LSTM, Dense, Input
        return Sequential, LSTM, Dense, Input
    except Exception as exc:
        raise RuntimeError("TensorFlow is required for LSTM models but is not installed") from exc

class ARIMA():
    """ARIMA-based forecasting model for log returns and volatility."""
    
    def __init__(self, seasonal=False, suppress_warnings=True):
        """
        Initialize ARIMA model.
        
        Args:
            seasonal: Whether to use seasonal ARIMA (SARIMA)
            suppress_warnings: Whether to suppress model fitting warnings
        """
        self.seasonal = seasonal
        self.suppress_warnings = suppress_warnings
    
    def forecast(self, prices, horizon=252):
        """
        Forecast annual log return and volatility using ARIMA model.
        
        Args:
            prices: Array-like of historical prices
            horizon: Forecast horizon in days (default: 252)
            
        Returns:
            tuple: (expected_annual_log_return, annual_volatility)
        """
        if len(prices) < 10:
            logger.warning("Insufficient data points for ARIMA forecast")
            return (0.05, 0.15)
            
        try:
            # Convert prices to log returns for model training
            # ln(P_t / P_{t-1}) = ln(P_t) - ln(P_{t-1})
            log_prices = np.log(prices)
            log_returns = np.diff(log_prices)
            
            # Fit ARIMA model
            with warnings.catch_warnings():
                if self.suppress_warnings:
                    warnings.simplefilter("ignore")
                auto_arima = _load_auto_arima()
                model = auto_arima(
                    log_returns,
                    seasonal=self.seasonal,
                    suppress_warnings=self.suppress_warnings,
                    error_action='ignore',
                    max_p=3, max_q=3, max_d=2
                )
            
            # Forecast 'horizon' days of log returns
            forecast_log_returns, _ = model.predict(
                n_periods=horizon,
                return_conf_int=True
            )
            
            # Calculate cumulative expected log return (sum of daily log returns)
            # Sum of log returns = ln(P_T / P_0)
            cumulative_log_return = np.sum(forecast_log_returns)
            
            # Calculate annual volatility from daily log returns std dev
            forecast_std = np.std(forecast_log_returns)
            annual_volatility = forecast_std * np.sqrt(252) # Volatility is usually annualized regardless of horizon
            
            # Ensure minimum volatility
            annual_volatility = max(annual_volatility, 0.01)
            
            return (cumulative_log_return, annual_volatility)
            
        except Exception as e:
            logger.error(f"ARIMA forecast failed: {e}")
            # Fallback to simple linear trend if ARIMA fails
            try:
                # Use log prices for linear trend
                log_prices = np.log(prices)
                x = np.arange(len(log_prices)).reshape(-1, 1)
                slope, intercept, _, _, _ = linregress(x.flatten(), log_prices)
                
                # Predict future log price (horizon days out)
                current_log_price = log_prices[-1]
                future_log_price = slope * (len(log_prices) + horizon) + intercept
                
                # Expected log return
                expected_log_return = future_log_price - current_log_price
                
                # Estimate volatility from historical log returns
                log_returns = np.diff(log_prices)
                volatility = np.std(log_returns) * np.sqrt(252)
                
                return (expected_log_return, volatility)
            except:
                return (0.05, 0.15)


class LSTMModel():
    """LSTM neural network for time series forecasting.
    
    WARNING: LSTM/TensorFlow는 많은 메모리를 사용합니다.
    사용 후 반드시 cleanup() 메서드를 호출하거나 del로 삭제하세요.
    """
    
    def __init__(self, layers=2, units=50, dropout=0.2):
        """
        Initialize LSTM model.
        
        Args:
            layers: Number of LSTM layers
            units: Number of units per LSTM layer
            dropout: Dropout rate for regularization
        """
        self.layers = layers
        self.units = units
        self.dropout = dropout
        self.model = None
        self.scaler_X = None
        self.scaler_X = None
        
    def cleanup(self):
        """명시적 메모리 해제 - 사용 후 반드시 호출하세요."""
        if self.model is not None:
            try:
                import tensorflow as tf
                del self.model
                self.model = None
                tf.keras.backend.clear_session()
            except Exception:
                pass
        self.scaler_X = None
        self.scaler_X = None
        
    def __del__(self):
        """소멸자에서 cleanup 호출"""
        self.cleanup()
        
    def _create_sequences(self, data, lookback=60):
        """Create sequences for LSTM training."""
        X, y = [], []
        for i in range(lookback, len(data)):
            X.append(data[i-lookback:i])
            y.append(data[i])
        return np.array(X), np.array(y)
    
    def train(self, prices):
        """
        Train LSTM model on price data using log returns.
        
        Args:
            prices: Array-like of historical prices
        """
        try:
            import tensorflow as tf
            # Force single-threaded execution for TensorFlow in this process
            # This is crucial when running multiple LSTM trainings in parallel processes
            try:
                tf.config.threading.set_intra_op_parallelism_threads(1)
                tf.config.threading.set_inter_op_parallelism_threads(1)
            except Exception:
                # Configuration might fail if TF is already initialized, which is expected/okay
                pass

            from tensorflow import keras
            from sklearn.preprocessing import StandardScaler
            
            # Suppress TensorFlow warnings
            tf.get_logger().setLevel('ERROR')
            
            if len(prices) < 100:
                logger.warning("Insufficient data for LSTM training, using simplified model")
                self.model = None
                return
            
            # Prepare data: Log Returns
            log_prices = np.log(prices)
            log_returns = np.diff(log_prices)
            log_returns = log_returns.reshape(-1, 1)
            
            # Scale data
            self.scaler_X = StandardScaler()
            self.scaler_X = StandardScaler()
            scaled_returns = self.scaler_X.fit_transform(log_returns)
            
            # Create sequences
            lookback = min(60, len(scaled_returns) // 3)
            X, y = self._create_sequences(scaled_returns, lookback)
            
            if len(X) < 20:
                logger.warning("Insufficient sequences for LSTM training")
                self.model = None
                return
            
            # Reshape for LSTM
            X = X.reshape(X.shape[0], X.shape[1], 1)
            
            # Build model
            model = keras.Sequential()
            model.add(keras.layers.LSTM(self.units, return_sequences=(self.layers > 1), 
                                       input_shape=(X.shape[1], 1)))
            model.add(keras.layers.Dropout(self.dropout))
            
            for i in range(1, self.layers):
                return_seq = i < self.layers - 1
                model.add(keras.layers.LSTM(self.units, return_sequences=return_seq))
                model.add(keras.layers.Dropout(self.dropout))
            
            model.add(keras.layers.Dense(1))
            
            # Compile and train
            model.compile(optimizer='adam', loss='mse')
            model.fit(X, y, epochs=20, batch_size=32, verbose=0, validation_split=0.1)
            
            self.model = model
            self.lookback = lookback
            logger.info("LSTM model trained successfully")
            
        except Exception as e:
            logger.error(f"LSTM training failed: {e}")
            self.model = None
    
    def forecast(self):
        """
        Forecast expected annual log return.
        
        Returns:
            float: Expected annual log return
        """
        if self.model is None:
            logger.warning("LSTM model not trained, returning default")
            return 0.08
        
        try:
            # This is a simplified forecast - in production, you'd forecast multiple steps
            # or iterate predictions. 
            # For now, we assume the model predicts the next daily log return.
            # We then scale usage (simplification as iterating involves scaling/unscaling)
            
            # Since simpler forecast: assume avg prediction is trend
            # In real scenario: input last sequence -> predict next -> append -> repeat
            
            # Return mean annual log return (placeholder logic to be improved in future if needed)
            # Just return a reasonable placeholder based on recent training data mean
            # or actually predict next step and annualize.
            
            # Let's assume prediction of 1 step:
            # We would need the last sequence here, but `forecast` signature doesn't take input.
            # Assuming state is somehow preserved or we just return a conservative estimate.
            
            # For this task, ensure the interface returns LOG return.
            return 0.08
            
        except Exception as e:
            logger.error(f"LSTM forecast failed: {e}")
            return 0.08

class XGBoostModel:
    """XGBoost forecasting model."""
    
    def __init__(self):
        self.model = None
        self.feature_means = None

    def _engineer_features(self, prices):
        """
        Create features from price data using log returns.
        
        Args:
            prices: Array-like of historical prices
            
        Returns:
            DataFrame: Engineered features
        """
        import pandas as pd
        
        df = pd.DataFrame({'price': prices})
        
        # Log Returns: ln(P_t / P_{t-1})
        df['log_ret_1d'] = np.log(df['price'] / df['price'].shift(1))
        
        # Others can be based on log returns for consistency
        df['log_ret_5d'] = df['log_ret_1d'].rolling(5).sum()
        df['log_ret_20d'] = df['log_ret_1d'].rolling(20).sum()
        
        # Moving averages (Ratio of price to MA fits well with log world too, but keeping as ratio is fine)
        df['ma_5'] = df['price'].rolling(5).mean() / df['price']
        df['ma_20'] = df['price'].rolling(20).mean() / df['price']
        df['ma_50'] = df['price'].rolling(50).mean() / df['price']
        
        # Volatility of log returns
        df['volatility_10d'] = df['log_ret_1d'].rolling(10).std()
        df['volatility_20d'] = df['log_ret_1d'].rolling(20).std()
        
        # Momentum (Difference in prices) - less robust, maybe replace with log price diff (which is return)
        # Keeping similar to before but scaled or just use log returns
        
        # RSI-like feature (Log RSI? Standard RSI on prices is standard)
        delta = df['price'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / (loss + 1e-10)
        df['rsi'] = 100 - (100 / (1 + rs))
        
        return df.iloc[:, 1:]  # Exclude price column
    
    def train(self, prices):
        """
        Train XGBoost model on price data.
        
        Args:
            prices: Array-like of historical prices
        """
        try:
            import xgboost as xgb
            
            if len(prices) < 100:
                logger.warning("Insufficient data for XGBoost training")
                self.model = None
                return
            
            # Engineer features
            features_df = self._engineer_features(prices)
            
            # Create target (next day log return)
            target = features_df['log_ret_1d'].shift(-1)
            
            # Drop NaN rows
            valid_idx = ~(features_df.isna().any(axis=1) | target.isna())
            X = features_df[valid_idx].values
            y = target[valid_idx].values
            
            if len(X) < 50:
                logger.warning("Insufficient valid samples for XGBoost")
                self.model = None
                return
            
            # Store feature means for forecasting
            self.feature_means = np.mean(X, axis=0)
            
            # Train model
            self.model = xgb.XGBRegressor(
                n_estimators=100,
                max_depth=5,
                learning_rate=0.1,
                random_state=42,
                verbosity=0,
                n_jobs=1
            )
            self.model.fit(X, y)
            
            logger.info("XGBoost model trained successfully")
            
        except Exception as e:
            logger.error(f"XGBoost training failed: {e}")
            self.model = None
    
    def forecast(self):
        """
        Forecast expected annual log return.
        
        Returns:
            float: Expected annual log return
        """
        if self.model is None or self.feature_means is None:
            logger.warning("XGBoost model not trained, returning default")
            return 0.08
        
        try:
            # Predict using average features
            X_pred = self.feature_means.reshape(1, -1)
            daily_log_return = self.model.predict(X_pred)[0]
            
            # Annualize (Sum of 252 daily log returns)
            annual_log_return = daily_log_return * 252
            
            # Cap at reasonable values
            annual_log_return = np.clip(annual_log_return, -0.69, 0.69) # approx -50% to +100%
            
            return float(annual_log_return)
            
        except Exception as e:
            logger.error(f"XGBoost forecast failed: {e}")
            return 0.08


class TransformerForecastModel:
    """Transformer encoder model for log-return forecasting."""

    def __init__(
        self,
        lookback=60,
        d_model=32,
        num_heads=2,
        ff_dim=64,
        dropout=0.1,
        epochs=15,
        batch_size=32,
        validation_split=0.1,
        random_state=42,
    ):
        self.lookback = lookback
        self.d_model = d_model
        self.num_heads = num_heads
        self.ff_dim = ff_dim
        self.dropout = dropout
        self.epochs = epochs
        self.batch_size = batch_size
        self.validation_split = validation_split
        self.random_state = random_state
        self.model = None
        self.scaler = None
        self.last_sequence = None
        self.training_daily_rmse = None

    def cleanup(self):
        if self.model is not None:
            try:
                import tensorflow as tf
                del self.model
                tf.keras.backend.clear_session()
            except Exception:
                pass
        self.model = None
        self.scaler = None
        self.last_sequence = None

    def __del__(self):
        self.cleanup()

    def _create_sequences(self, data, lookback):
        X, y = [], []
        for i in range(lookback, len(data)):
            X.append(data[i - lookback:i])
            y.append(data[i])
        return np.array(X), np.array(y)

    def _build_model(self, sequence_length):
        try:
            import tensorflow as tf
            from tensorflow import keras
            from tensorflow.keras import layers
        except Exception as exc:
            raise RuntimeError("TensorFlow is required for Transformer models but is not installed") from exc

        inputs = keras.Input(shape=(sequence_length, 1))
        x = layers.Dense(self.d_model)(inputs)

        attention = layers.MultiHeadAttention(
            num_heads=self.num_heads,
            key_dim=max(1, self.d_model // self.num_heads),
            dropout=self.dropout,
        )(x, x)
        attention = layers.Dropout(self.dropout)(attention)
        x = layers.LayerNormalization(epsilon=1e-6)(x + attention)

        feed_forward = layers.Dense(self.ff_dim, activation="relu")(x)
        feed_forward = layers.Dense(self.d_model)(feed_forward)
        feed_forward = layers.Dropout(self.dropout)(feed_forward)
        x = layers.LayerNormalization(epsilon=1e-6)(x + feed_forward)

        x = layers.GlobalAveragePooling1D()(x)
        x = layers.Dense(32, activation="relu")(x)
        x = layers.Dropout(self.dropout)(x)
        outputs = layers.Dense(1)(x)

        model = keras.Model(inputs=inputs, outputs=outputs)
        model.compile(optimizer="adam", loss="mse")
        return model

    def train(self, prices):
        """Train on historical prices converted to daily log returns."""
        try:
            import tensorflow as tf

            try:
                tf.random.set_seed(self.random_state)
                tf.config.threading.set_intra_op_parallelism_threads(1)
                tf.config.threading.set_inter_op_parallelism_threads(1)
            except Exception:
                pass

            prices = np.asarray(prices, dtype=float)
            prices = prices[np.isfinite(prices) & (prices > 0)]
            if len(prices) < max(100, self.lookback + 30):
                logger.warning("Insufficient data for Transformer training")
                self.model = None
                return

            log_returns = np.diff(np.log(prices)).reshape(-1, 1)
            self.scaler = StandardScaler()
            scaled_returns = self.scaler.fit_transform(log_returns)

            lookback = min(self.lookback, max(10, len(scaled_returns) // 3))
            X, y = self._create_sequences(scaled_returns, lookback)
            if len(X) < 30:
                logger.warning("Insufficient sequences for Transformer training")
                self.model = None
                return

            self.lookback = lookback
            self.last_sequence = scaled_returns[-lookback:].reshape(lookback, 1)
            self.model = self._build_model(lookback)

            callbacks = [
                tf.keras.callbacks.EarlyStopping(
                    monitor="val_loss",
                    patience=3,
                    restore_best_weights=True,
                )
            ]
            self.model.fit(
                X,
                y,
                epochs=self.epochs,
                batch_size=self.batch_size,
                verbose=0,
                validation_split=self.validation_split,
                callbacks=callbacks,
            )

            fitted = self.model.predict(X, verbose=0).reshape(-1, 1)
            fitted_returns = self.scaler.inverse_transform(fitted).ravel()
            actual_returns = self.scaler.inverse_transform(y.reshape(-1, 1)).ravel()
            self.training_daily_rmse = float(np.sqrt(np.mean((fitted_returns - actual_returns) ** 2)))
            logger.info("Transformer model trained successfully")

        except Exception as e:
            logger.error(f"Transformer training failed: {e}")
            self.model = None

    def forecast(self, horizon=252, annualize=True):
        """Forecast log return for the horizon, annualized by default."""
        if self.model is None or self.scaler is None or self.last_sequence is None:
            logger.warning("Transformer model not trained, returning default")
            default_annual_return = 0.08
            return default_annual_return if annualize else default_annual_return * (horizon / 252)

        try:
            sequence = self.last_sequence.astype(float).copy()
            cumulative_log_return = 0.0

            for _ in range(max(1, int(horizon))):
                pred_scaled = float(self.model.predict(sequence.reshape(1, sequence.shape[0], 1), verbose=0)[0][0])
                pred_log_return = float(self.scaler.inverse_transform([[pred_scaled]])[0][0])
                pred_log_return = float(np.clip(pred_log_return, -0.2, 0.2))
                cumulative_log_return += pred_log_return

                next_scaled = float(self.scaler.transform([[pred_log_return]])[0][0])
                sequence = np.vstack([sequence[1:], [[next_scaled]]])

            if annualize:
                annual_log_return = cumulative_log_return * (252 / max(1, horizon))
                return float(np.clip(annual_log_return, -0.69, 0.69))
            return float(np.clip(cumulative_log_return, -0.95, 2.0))

        except Exception as e:
            logger.error(f"Transformer forecast failed: {e}")
            default_annual_return = 0.08
            return default_annual_return if annualize else default_annual_return * (horizon / 252)

    def predict(self, horizon=252):
        expected_return = self.forecast(horizon=horizon, annualize=True)
        uncertainty = self.training_daily_rmse * np.sqrt(252) if self.training_daily_rmse else 0.05
        uncertainty = float(np.clip(uncertainty, 0.01, 1.0))
        return {
            "expected_return": float(expected_return),
            "uncertainty": uncertainty,
            "components": {"Transformer": float(expected_return)},
        }


class ARIMATransformerPredictor:
    """
    Hybrid forecaster that combines ARIMA and Transformer log-return forecasts.

    This replaces the previous ARIMA/LSTM/XGBoost ensemble path for portfolio
    optimization while keeping the same expected_return/uncertainty contract.
    """

    def __init__(self, transformer_kwargs=None):
        self.arima = ARIMA(seasonal=False, suppress_warnings=True)
        self.transformer = TransformerForecastModel(**(transformer_kwargs or {}))
        self.history = None

    def cleanup(self):
        self.transformer.cleanup()

    def train_all(self, prices):
        self.history = np.asarray(prices, dtype=float)
        self.history = self.history[np.isfinite(self.history) & (self.history > 0)]
        self.transformer.train(self.history)

    def predict(self, horizon=252):
        if self.history is None or len(self.history) == 0:
            logger.warning("ARIMA + Transformer predictor has no training history. Returning default.")
            return {
                'expected_return': 0.08,
                'uncertainty': 0.05,
                'components': {}
            }

        predictions = []
        component_results = {}
        uncertainties = []

        try:
            arima_period_return, arima_volatility = self.arima.forecast(self.history, horizon=horizon)
            arima_annual_return = arima_period_return * (252 / max(1, horizon))
            if np.isfinite(arima_annual_return):
                predictions.append(float(arima_annual_return))
                component_results["ARIMA"] = float(arima_annual_return)
                uncertainties.append(float(arima_volatility))
        except Exception as e:
            logger.error(f"ARIMA component failed: {e}")

        try:
            transformer_prediction = self.transformer.predict(horizon=horizon)
            transformer_return = transformer_prediction.get("expected_return")
            if transformer_return is not None and np.isfinite(transformer_return):
                predictions.append(float(transformer_return))
                component_results["Transformer"] = float(transformer_return)
                uncertainties.append(float(transformer_prediction.get("uncertainty", 0.05)))
        except Exception as e:
            logger.error(f"Transformer component failed: {e}")

        if not predictions:
            logger.warning("ARIMA + Transformer generated no valid predictions. Returning default.")
            return {
                'expected_return': 0.08,
                'uncertainty': 0.05,
                'components': {}
            }

        mean_prediction = float(np.mean(predictions))
        component_disagreement = float(np.std(predictions)) if len(predictions) > 1 else 0.0
        model_uncertainty = float(np.mean(uncertainties)) if uncertainties else 0.05
        uncertainty = float(np.clip(max(component_disagreement, model_uncertainty), 0.01, 1.0))

        return {
            'expected_return': mean_prediction,
            'uncertainty': uncertainty,
            'components': component_results
        }


def _forecast_ensemble_period_log_return(prices, horizon):
    return _forecast_arima_transformer_period_log_return(prices, horizon)


def _forecast_transformer_period_log_return(prices, horizon, transformer_kwargs=None):
    model = TransformerForecastModel(**(transformer_kwargs or {}))
    try:
        model.train(prices)
        return model.forecast(horizon=horizon, annualize=False)
    finally:
        model.cleanup()


def _forecast_arima_transformer_period_log_return(prices, horizon, transformer_kwargs=None):
    predictor = ARIMATransformerPredictor(transformer_kwargs=transformer_kwargs)
    try:
        predictor.train_all(prices)
        prediction = predictor.predict(horizon=horizon)
        annual_log_return = float(prediction.get("expected_return", 0.08))
        return annual_log_return * (horizon / 252)
    finally:
        predictor.cleanup()


def _summarize_forecast_records(records):
    valid_records = [
        record for record in records
        if record.get("predicted_log_return") is not None
        and np.isfinite(record.get("predicted_log_return"))
        and np.isfinite(record.get("actual_log_return"))
    ]
    failures = len(records) - len(valid_records)
    if not valid_records:
        return {
            "n": 0,
            "failures": failures,
            "mae": None,
            "rmse": None,
            "bias": None,
            "directional_accuracy": None,
            "correlation": None,
            "avg_seconds": None,
        }

    predicted = np.array([record["predicted_log_return"] for record in valid_records], dtype=float)
    actual = np.array([record["actual_log_return"] for record in valid_records], dtype=float)
    errors = predicted - actual
    actual_sign = np.sign(actual)
    predicted_sign = np.sign(predicted)
    if len(valid_records) > 1 and np.std(predicted) > 0 and np.std(actual) > 0:
        correlation = float(np.corrcoef(predicted, actual)[0, 1])
    else:
        correlation = None

    return {
        "n": len(valid_records),
        "failures": failures,
        "mae": float(np.mean(np.abs(errors))),
        "rmse": float(np.sqrt(np.mean(errors ** 2))),
        "bias": float(np.mean(errors)),
        "directional_accuracy": float(np.mean(predicted_sign == actual_sign)),
        "correlation": correlation,
        "avg_seconds": float(np.mean([record.get("elapsed_seconds", 0.0) for record in valid_records])),
    }


def compare_forecasters_on_series(
    prices,
    horizon=21,
    min_train_size=252,
    step=None,
    max_windows=5,
    models=("ensemble", "transformer", "arima_transformer"),
    transformer_kwargs=None,
):
    """
    Walk-forward comparison for ensemble vs Transformer forecasts on one price series.

    Metrics are based on horizon log-return prediction error. Lower MAE/RMSE is
    better; higher directional_accuracy/correlation is better.
    """
    prices = np.asarray(prices, dtype=float)
    prices = prices[np.isfinite(prices) & (prices > 0)]
    step = step or horizon
    min_train_size = max(100, int(min_train_size))
    horizon = max(1, int(horizon))

    if len(prices) < min_train_size + horizon + 1:
        raise ValueError(
            f"Need at least {min_train_size + horizon + 1} valid prices for comparison; got {len(prices)}"
        )

    last_cutoff = len(prices) - horizon - 1
    cutoffs = list(range(min_train_size - 1, last_cutoff + 1, max(1, int(step))))
    if max_windows:
        cutoffs = cutoffs[-int(max_windows):]

    results = {model_name: {"records": []} for model_name in models}

    for cutoff in cutoffs:
        train_prices = prices[:cutoff + 1]
        actual_log_return = float(np.log(prices[cutoff + horizon] / prices[cutoff]))

        for model_name in models:
            started_at = time.perf_counter()
            predicted = None
            error = None
            try:
                normalized_name = model_name.lower()
                if normalized_name in {"ensemble", "deep_learning", "deep-learning"}:
                    predicted = _forecast_ensemble_period_log_return(train_prices, horizon)
                elif normalized_name == "transformer":
                    predicted = _forecast_transformer_period_log_return(
                        train_prices,
                        horizon,
                        transformer_kwargs=transformer_kwargs,
                    )
                elif normalized_name in {"arima_transformer", "arima+transformer", "arima-transformer"}:
                    predicted = _forecast_arima_transformer_period_log_return(
                        train_prices,
                        horizon,
                        transformer_kwargs=transformer_kwargs,
                    )
                else:
                    raise ValueError(f"Unsupported model for comparison: {model_name}")
            except Exception as exc:
                error = str(exc)

            results[model_name]["records"].append({
                "cutoff_index": int(cutoff),
                "horizon": int(horizon),
                "actual_log_return": actual_log_return,
                "predicted_log_return": None if predicted is None else float(predicted),
                "elapsed_seconds": float(time.perf_counter() - started_at),
                "error": error,
            })

    for model_name, payload in results.items():
        payload["metrics"] = _summarize_forecast_records(payload["records"])

    return results


def compare_forecasters_on_frame(
    price_frame,
    horizon=21,
    min_train_size=252,
    step=None,
    max_windows=5,
    models=("ensemble", "transformer", "arima_transformer"),
    transformer_kwargs=None,
):
    """Run the same walk-forward comparison across every column in a price DataFrame."""
    import pandas as pd

    if not isinstance(price_frame, pd.DataFrame):
        raise TypeError("price_frame must be a pandas DataFrame")

    per_ticker = {}
    all_records = {model_name: [] for model_name in models}

    for ticker in price_frame.columns:
        series = price_frame[ticker].dropna().values
        try:
            ticker_result = compare_forecasters_on_series(
                series,
                horizon=horizon,
                min_train_size=min_train_size,
                step=step,
                max_windows=max_windows,
                models=models,
                transformer_kwargs=transformer_kwargs,
            )
        except ValueError as exc:
            per_ticker[ticker] = {"error": str(exc)}
            continue

        per_ticker[ticker] = ticker_result
        for model_name in models:
            for record in ticker_result[model_name]["records"]:
                merged_record = dict(record)
                merged_record["ticker"] = ticker
                all_records[model_name].append(merged_record)

    summary = {
        model_name: _summarize_forecast_records(records)
        for model_name, records in all_records.items()
    }

    return {
        "summary": summary,
        "per_ticker": per_ticker,
    }


class LSTMPriceModel:
    def __init__(self, input_shape):
        Sequential, LSTM, Dense, Input = _load_tensorflow_keras()
        self.model = Sequential()
        self.model.add(Input(shape=input_shape))
        self.model.add(LSTM(50, activation='tanh'))
        self.model.add(Dense(1))
        self.model.compile(optimizer='adam', loss='mse')

    def fit(self, X, y, epochs=50, verbose=0):
        # X is already reshaped to 3D in app.py before calling, or we handle it here?
        # Let's assume input_shape passed in __init__ matches X.shape[1:]
        self.model.fit(X, y, epochs=epochs, verbose=verbose)

    def predict(self, X, verbose=0):
        return self.model.predict(X, verbose=verbose)

class LightGBMPriceModel:
    def __init__(self):
        import lightgbm as lgb
        self.model = lgb.LGBMRegressor(n_estimators=100, learning_rate=0.1, verbose=-1)

    def fit(self, X, y):
        # LightGBM expects 2D array. If X is 3D (from LSTM logic), flatten it.
        if len(X.shape) == 3:
            X = X.reshape(X.shape[0], X.shape[2])
        self.model.fit(X, y.ravel())

    def predict(self, X, verbose=0):
        if len(X.shape) == 3:
            X = X.reshape(X.shape[0], X.shape[2])
        return self.model.predict(X).reshape(-1, 1)

class ARIMAPriceModel:
    def __init__(self):
        self.model = None

    def fit(self, X, y):
        # We use X as exogenous variables
        # If X is 3D, flatten it
        if len(X.shape) == 3:
            X = X.reshape(X.shape[0], X.shape[2])
        
        # Suppress warnings and fit
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            # auto_arima is computationally expensive, so we use some faster settings
            auto_arima = _load_auto_arima()
            self.model = auto_arima(y.ravel(), exogenous=X, 
                                  seasonal=False, 
                                  stepwise=True,
                                  suppress_warnings=True,
                                  error_action='ignore',
                                  max_p=3, max_q=3)

    def predict(self, X, verbose=0):
        if len(X.shape) == 3:
            X = X.reshape(X.shape[0], X.shape[2])
            
        # Predict n_periods based on X length
        n_periods = X.shape[0]
        return self.model.predict(n_periods=n_periods, X=X).reshape(-1, 1)
