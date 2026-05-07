from flask import Flask, jsonify, request
from flask_cors import CORS
import numpy as np
import yfinance as yf
import warnings
from datetime import datetime, timedelta
import pandas as pd
from hedge_analysis import analyze_hedge_relationship
from portfolio_benchmark import calculate_portfolio_benchmark
from pmdarima import auto_arima


from forecast_models import LSTMPriceModel, LightGBMPriceModel, ARIMAPriceModel
from sklearn.preprocessing import MinMaxScaler, StandardScaler
from financial_statement import get_financial_ratios, get_financial_statements
from portfolio_optimization import (
    optimize_portfolio,
    load_portfolio_result,
    list_saved_portfolios,
    manage_portfolio_logic,
    _convert_price_data_to_usd,
    BASE_CURRENCY
)
from stock_screener import search_stocks


app = Flask(__name__)

CORS(app, 
     resources={
         "/*": {
             "origins": ["http://localhost:5173", "http://127.0.0.1:*"],
             "methods": ["GET", "POST", "OPTIONS"],
             "allow_headers": ["Content-Type", "Authorization", "Accept"],
             "supports_credentials": True,
             "expose_headers": ["Content-Type", "Authorization"],
             "max_age": 3600
         }
     })

def validate_date_range(start_date, end_date):
    try:
        start_date = datetime.strptime(start_date, '%Y-%m-%d')
        end_date = datetime.strptime(end_date, '%Y-%m-%d')
        
        # Check if dates are valid
        if start_date >= end_date:
            raise ValueError("Start date must be before end date")
            
        # Check if dates are not in the future
        if end_date > datetime.now():
            raise ValueError("End date cannot be in the future")
            
        return start_date, end_date
    except ValueError as e:
        raise ValueError(f"Invalid date range: {str(e)}")
    except Exception as e:
        raise ValueError(f"Invalid date format. Please use YYYY-MM-DD format")


def normalize_history_close_to_usd(ticker, df, start_date, end_date):
    """Normalize a yfinance history dataframe's Close column into USD for charting."""
    if df.empty or 'Close' not in df.columns:
        return df, BASE_CURRENCY, {}

    close_frame = pd.DataFrame({ticker: df['Close']})
    converted, currency_metadata, conversion_failures = _convert_price_data_to_usd(
        close_frame,
        start_date,
        end_date
    )

    if conversion_failures or ticker not in converted.columns:
        raise ValueError(f"Could not convert {ticker} prices to {BASE_CURRENCY}.")

    normalized_df = df.copy()
    normalized_df['Close'] = converted[ticker].reindex(normalized_df.index)

    return normalized_df, BASE_CURRENCY, currency_metadata.get(ticker, {})

def generate_regression_data(ticker="", start_date=None, end_date=None, future_days=0, model_type='LSTM'):
    try:
        if start_date and end_date:
            start_date, end_date = validate_date_range(start_date, end_date)
        else:
            end_date = datetime.now() - timedelta(days=1)
            start_date = end_date - timedelta(days=90)
        
        print(f"Fetching {ticker} data from {start_date} to {end_date} using {model_type}")
        
        # fetch stock data
        stock = yf.Ticker(ticker)
        df = stock.history(start=start_date.strftime('%Y-%m-%d'), 
                          end=end_date.strftime('%Y-%m-%d'))
        
        if df.empty:
            print(f"No data received from yfinance for {ticker}")
            return {}

        df, price_currency, currency_metadata = normalize_history_close_to_usd(ticker, df, start_date, end_date)

        # ARIMA should model the original time series directly.
        # Do not force ARIMA into the feature-based regression pipeline used by LSTM/LightGBM.
        if model_type == 'ARIMA':
            close_series = df['Close'].dropna()
            if len(close_series) < 30:
                print(f"Not enough data for ARIMA on {ticker}")
                return {}

            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                arima_model = auto_arima(
                    close_series.values,
                    seasonal=False,
                    stepwise=True,
                    suppress_warnings=True,
                    error_action='ignore',
                    max_p=3,
                    max_q=3,
                    max_d=2
                )

            fitted_prices = np.asarray(arima_model.predict_in_sample(), dtype=float)

            # ARIMA with differencing (d > 0) can produce unstable leading fitted values
            # because the first states are not fully initialized.
            # Replace the first d points with observed prices for a visually consistent chart.
            d_order = 0
            try:
                d_order = int(arima_model.order[1])
            except Exception:
                d_order = 0

            if d_order > 0:
                fitted_prices[:d_order] = close_series.values[:d_order]

            # Defensive fallback for rare edge cases where the first point is still non-finite.
            if len(fitted_prices) > 0 and not np.isfinite(fitted_prices[0]):
                fitted_prices[0] = float(close_series.values[0])

            dates = close_series.index.strftime('%Y-%m-%d').tolist()
            original_data = {date: float(price) for date, price in zip(dates, close_series.values)}
            regression_data = {date: float(price) for date, price in zip(dates, fitted_prices)}

            future_predictions = {}
            if future_days > 0:
                future_prices = arima_model.predict(n_periods=future_days)
                last_date = close_series.index[-1]
                for i, predicted_price in enumerate(future_prices, start=1):
                    next_date = last_date + timedelta(days=i)
                    future_predictions[next_date.strftime('%Y-%m-%d')] = float(predicted_price)

            info = stock.info
            company_name = info.get('longName', ticker)

            return {
                'prices': original_data,
                'regression': regression_data,
                'future_predictions': future_predictions,
                'companyName': company_name,
                'price_currency': price_currency,
                'source_currency': currency_metadata.get('source_currency', price_currency),
                'slope': 'N/A',
                'intercept': 'N/A'
            }
            
        # Feature Engineering: Create features that might predict the *change* in price
        df['Time'] = np.arange(len(df))
        df['MA7'] = df['Close'].rolling(window=7).mean()
        df['MA21'] = df['Close'].rolling(window=21).mean()
        df['Lag1'] = df['Close'].shift(1)
        
        # Target variable: Daily change in price
        df['Price_Change'] = df['Close'].diff()

        # Drop rows with NaN values
        df.dropna(inplace=True)
        
        if df.empty:
            print(f"Not enough data for {ticker} after feature engineering. Consider a longer date range.")
            return {}
            
        # Prepare data for regression        
        feature_columns = ['Time', 'MA7', 'MA21', 'Lag1', 'Volume']
        X = df[feature_columns].values
        
        # Target variable: Price Change
        y = df['Price_Change'].values.reshape(-1, 1) # Predict the change, not the absolute price
        
        # Scale data
        # Use Standard Scaler for Price Change to center around 0
        scaler_X = MinMaxScaler(feature_range=(0, 1))
        scaler_y = StandardScaler()
        
        X_scaled = scaler_X.fit_transform(X)
        y_scaled = scaler_y.fit_transform(y)
        
        # Reshape for LSTM: (samples, time_steps, features)
        X_reshaped = X_scaled.reshape((X_scaled.shape[0], 1, X_scaled.shape[1]))
        
        # Select and train model
        input_shape = (1, X_scaled.shape[1])
        if model_type == 'LightGBM':
            model = LightGBMPriceModel()
        elif model_type == 'ARIMA':
            model = ARIMAPriceModel()
        else:
            model = LSTMPriceModel(input_shape)

        # Fit model
        model.fit(X_reshaped, y_scaled)

        predicted_changes_scaled = model.predict(X_reshaped)
        predicted_changes = scaler_y.inverse_transform(predicted_changes_scaled).flatten()
        
        # The regression line is the cumulative sum of predicted changes, starting from the price before the first prediction
        # Since we dropped the first row, df['Lag1'].iloc[0] is the Close price of the dropped row (t-1)
        initial_price = df['Lag1'].iloc[0]
        regression_line = initial_price + np.cumsum(predicted_changes)
        
        # Convert to date:value format
        dates = df.index.strftime('%Y-%m-%d').tolist()
        original_data = {date: float(price) for date, price in zip(dates, df['Close'])}
        regression_data = {date: float(price) for date, price in zip(dates, regression_line)}
        
        # Get stock info
        info = stock.info
        company_name = info.get('longName', ticker)

        future_predictions = {}
        if future_days > 0 and not X_reshaped.size == 0:
            last_known_price = df['Close'].iloc[-1]
            last_date = df.index[-1]

            # Use the last row of features as the starting point for future predictions.
            # Keep MA/Volume constant as a lightweight approximation.
            last_features = df[feature_columns].iloc[-1:].copy()

            for i in range(future_days):
                # Scale input for prediction
                last_features_scaled = scaler_X.transform(last_features.values)
                last_features_reshaped = last_features_scaled.reshape((1, 1, last_features_scaled.shape[1]))

                # Predict the change for the next day
                predicted_change_scaled = model.predict(last_features_reshaped, verbose=0)
                predicted_change = scaler_y.inverse_transform(predicted_change_scaled)[0][0]

                # Calculate the new price
                next_price = last_known_price + predicted_change

                # Update features for the next iteration
                next_date = last_date + timedelta(days=i + 1)

                last_features['Time'] += 1
                last_features['Lag1'] = last_known_price

                # Store prediction
                future_predictions[next_date.strftime('%Y-%m-%d')] = float(next_price)

                # Update last known price for the next prediction
                last_known_price = next_price
        
        return {
            'prices': original_data,
            'regression': regression_data,
            'future_predictions': future_predictions,
            'companyName': company_name,
            'price_currency': price_currency,
            'source_currency': currency_metadata.get('source_currency', price_currency),
            'slope': 'N/A',
            'intercept': 'N/A'
        }
        
    except Exception as e:
        print(f"Error generating regression data: {str(e)}")
        return {
            'prices': {},
            'regression': {},
            'companyName': ticker, 
            'price_currency': BASE_CURRENCY,
            'source_currency': BASE_CURRENCY,
            'slope': 'N/A', 
            'intercept': 'N/A',
            'future_predictions': {}
        }

def generate_data(ticker="", start_date=None, end_date=None):
    try:
        # use provided dates or default to 3 months from 'yesterday'
        if start_date and end_date:
            start_date, end_date = validate_date_range(start_date, end_date)
        else:
            end_date = datetime.now() - timedelta(days=1)
            start_date = end_date - timedelta(days=90)
        
        print(f"Fetching {ticker} data from {start_date} to {end_date}")
        
        # fetch stock data
        stock = yf.Ticker(ticker)
        df = stock.history(start=start_date.strftime('%Y-%m-%d'), 
                          end=end_date.strftime('%Y-%m-%d'))
        
        if df.empty:
            print(f"No data received from yfinance for {ticker}")
            return {}

        df, price_currency, currency_metadata = normalize_history_close_to_usd(ticker, df, start_date, end_date)
            
        print(f"DataFrame shape: {df.shape}")
        print(f"DataFrame columns: {df.columns}")
        print(f"First few rows:\n{df.head()}")
        
        # get stock info
        info = stock.info
        company_name = info.get('longName', ticker)
        
        # convert to date:value format
        data = {date.strftime('%Y-%m-%d'): float(price) for date, price in zip(df.index, df['Close'])}
        print(f"Generated data dictionary with {len(data)} entries")
        
        return {
            'prices': data,
            'companyName': company_name,
            'price_currency': price_currency,
            'source_currency': currency_metadata.get('source_currency', price_currency),
            'regression': {},
            'future_predictions': {}
        }
        
    except Exception as e:
        print(f"Error fetching data: {str(e)}")
        return {
            'prices': {},
            'companyName': ticker,
            'price_currency': BASE_CURRENCY,
            'source_currency': BASE_CURRENCY,
            'regression': {},
            'future_predictions': {}
        }
    

    
# API endpoint to send data to the frontend
@app.route('/get-data', methods=['GET', 'OPTIONS'])
def get_data():
    ticker = request.args.get('ticker', 'AAPL')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    include_regression = request.args.get('regression', 'false').lower() == 'true'
    future_days_str = request.args.get('future_days', '0')
    model_type = request.args.get('model', 'LSTM')
    
    try:
        future_days = int(future_days_str)
        if future_days < 0:
            future_days = 0 # Prevent negative days
    except ValueError:
        future_days = 0 # Default to 0 if conversion fails

    if include_regression:
        data = generate_regression_data(ticker, start_date, end_date, future_days=future_days, model_type=model_type)
    else:
        # Default data gen doesn't use model
        data = generate_data(ticker, start_date, end_date)

    return jsonify(data)

# add new endpoint for hedge analysis
@app.route('/analyze-hedge', methods=['GET', 'OPTIONS'])
def analyze_hedge():
    ticker1 = request.args.get('ticker1')
    ticker2 = request.args.get('ticker2')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    if not ticker1 or not ticker2:
        return jsonify({'error': 'Both tickers are required'}), 400

    result = analyze_hedge_relationship(ticker1, ticker2, start_date, end_date)
    return jsonify(result)



@app.route('/financial-statement', methods=['GET'])
def financial_statement():
    print("--- Received request for financial statement ---")
    ticker = request.args.get('ticker')
    statement_type = request.args.get('type')
    frequency = request.args.get('frequency', 'annual')

    if not ticker:
        return jsonify({"error": "Ticker symbol is required"}), 400

    if statement_type:
        data = get_financial_statements(ticker, statement_type, frequency)
    else:
        # Default to ratios for backward compatibility or initial view
        data = get_financial_ratios(ticker)

    if 'error' in data:
        # If it's just a "unavailable data" error, we might still want to return 200 with the error message
        # But 404 is fine if it really failed.
        return jsonify(data), 404

    return jsonify(data)

import queue
import threading
import json
from flask import Response, stream_with_context

# Global store for request queues: {request_id: queue.Queue}
REQUEST_QUEUES = {}

def push_progress(request_id, progress, total, message, status='running'):
    """Helper to push progress events to the SSE queue."""
    if request_id in REQUEST_QUEUES:
        q = REQUEST_QUEUES[request_id]
        if status == 'completed':
            q.put({'type': 'complete', 'progress': 100, 'message': 'Optimization complete'})
            q.put(None) # Sentinel to close stream
        elif status == 'error':
            q.put({'type': 'error', 'message': message})
            q.put(None)
        else:
            percentage = int((progress / total) * 100) if total > 0 else 0
            q.put({'type': 'progress', 'progress': percentage, 'message': message})

@app.route('/api/progress-stream/<request_id>', methods=['GET'])
def stream_progress(request_id):
    def event_stream():
        # Lazy initialization: Allow connecting before POST
        if request_id not in REQUEST_QUEUES:
             REQUEST_QUEUES[request_id] = queue.Queue()
        
        q = REQUEST_QUEUES[request_id]
        while True:
            try:
                # Wait for next event
                event = q.get(timeout=600) # 10 min timeout
                if event is None:
                    break
                
                # Format as SSE
                yield f"event: {event['type']}\ndata: {json.dumps(event)}\n\n"
            except queue.Empty:
                yield f"event: ping\ndata: keep-alive\n\n"
            except Exception as e:
                app.logger.error(f"SSE stream error: {str(e)}")
                break
        
        # Cleanup
        if request_id in REQUEST_QUEUES:
            del REQUEST_QUEUES[request_id]

    return Response(stream_with_context(event_stream()), mimetype="text/event-stream")

@app.route('/api/optimize-portfolio', methods=['POST'])
def optimize_portfolio_endpoint():
    data = request.get_json()
    
    ticker_group = data.get('ticker_group')
    tickers = data.get('tickers')
    start_date = data.get('start_date')
    end_date = data.get('end_date')
    risk_free_rate = data.get('risk_free_rate')
    target_return = data.get('target_return')
    risk_tolerance = data.get('risk_tolerance')
    portfolio_id = data.get('portfolio_id')
    persist_result = bool(data.get('persist_result'))
    load_if_available = bool(data.get('load_if_available'))
    request_id = data.get('request_id')
    forecast_method = data.get('forecast_method', 'LIGHTWEIGHT')
    optimization_method = data.get('optimization_method', 'BL')
    
    # Advanced settings
    forecast_horizon = int(data.get('forecast_horizon', 252))
    min_history = int(data.get('min_history', 100))
    bl_tau = float(data.get('bl_tau', 0.05))

    if not request_id:
        return jsonify({"error": "request_id is required"}), 400

    # Initialize Queue for SSE (Idempotent)
    if request_id not in REQUEST_QUEUES:
        REQUEST_QUEUES[request_id] = queue.Queue()

    def background_optimization(req_id, params):
        try:
            # Define callback adapter for weighted progress
            def progress_adapter(current, total, message):
                push_progress(req_id, current, total, message, status='running')

            result = optimize_portfolio(
                start_date=params['start_date'],
                end_date=params['end_date'],
                risk_free_rate=params['risk_free_rate'],
                ticker_group=params['ticker_group'],
                tickers=params['tickers'],
                target_return=params['target_return'],
                risk_tolerance=params['risk_tolerance'],
                portfolio_id=params['portfolio_id'],
                persist_result=params['persist_result'],
                load_if_available=params['load_if_available'],
                progress_callback=progress_adapter,
                forecast_method=params.get('forecast_method', 'LIGHTWEIGHT'),
                optimization_method=params.get('optimization_method', 'BL'),
                forecast_horizon=params.get('forecast_horizon', 252),
                min_history=params.get('min_history', 100),
                bl_tau=params.get('bl_tau', 0.05)
            )

            if "error" in result:
                push_progress(req_id, 0, 0, result["error"], status='error')
            else:
                 # Send result in complete message
                 q = REQUEST_QUEUES[req_id]
                 q.put({'type': 'complete', 'progress': 100, 'message': 'Optimization complete', 'result': result})
                 q.put(None)

        except Exception as e:
            app.logger.error(f"Background optimization failed: {e}")
            push_progress(req_id, 0, 0, str(e), status='error')

    # Start background thread
    params = {
        'ticker_group': ticker_group, 'tickers': tickers, 'start_date': start_date, 
        'end_date': end_date, 'risk_free_rate': risk_free_rate, 'target_return': target_return,
        'risk_tolerance': risk_tolerance, 'portfolio_id': portfolio_id, 
        'persist_result': persist_result, 'load_if_available': load_if_available,
        'forecast_method': forecast_method, 'optimization_method': optimization_method,
        'forecast_horizon': forecast_horizon, 'bl_tau': bl_tau,
        'min_history': min_history
    }
    thread = threading.Thread(target=background_optimization, args=(request_id, params))
    thread.daemon = True
    thread.start()

    return jsonify({"message": "Optimization started", "request_id": request_id})


@app.route('/api/portfolio-results', methods=['GET'])
def list_portfolio_results_endpoint():
    try:
        return jsonify({'portfolio_ids': list_saved_portfolios()})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/portfolio-results/<portfolio_id>', methods=['GET'])
def get_portfolio_result_endpoint(portfolio_id):
    result = load_portfolio_result(portfolio_id)
    if not result:
        return jsonify({'error': f'Portfolio {portfolio_id} not found'}), 404
    return jsonify(result)

@app.route('/api/stock-screener', methods=['POST'])
def stock_screener_endpoint():
    data = request.get_json()
    if not data or 'filters' not in data:
        return jsonify({"error": "Request must be JSON and contain a 'filters' key"}), 400

    filters = data.get('filters')
    if not isinstance(filters, dict):
        return jsonify({"error": "'filters' must be a dictionary"}), 400

    try:
        results = search_stocks(filters)
        return jsonify(results)
    except Exception as e:
        # Log the exception for debugging
        app.logger.error(f"Stock screener failed with exception: {e}")
        return jsonify({"error": "An internal error occurred while screening stocks."}), 500

@app.route('/api/benchmark-portfolio', methods=['POST'])
def benchmark_portfolio_endpoint():
    """
    Benchmark a portfolio against S&P 500 and risk-free assets.
    
    Request JSON:
        portfolio_data: dict with weights and prices
        budget: float (investment amount)
        start_date: string (YYYY-MM-DD format)
        end_date: string (YYYY-MM-DD format)
        risk_free_rate: float (annual rate as decimal, e.g., 0.04)
    
    Returns:
        JSON with portfolio_timeline, sp500_timeline, riskfree_timeline, and summary
    """
    try:
        data = request.get_json()
        
        # Validate request data
        if not data:
            return jsonify({'error': 'Request must be JSON'}), 400
        
        required_fields = ['portfolio_data', 'budget', 'start_date', 'end_date', 'risk_free_rate']
        missing_fields = [field for field in required_fields if field not in data]
        
        if missing_fields:
            return jsonify({
                'error': f'Missing required fields: {", ".join(missing_fields)}'
            }), 400
        
        # Extract and validate parameters
        portfolio_data = data.get('portfolio_data')
        budget = data.get('budget')
        start_date_str = data.get('start_date')
        end_date_str = data.get('end_date')
        risk_free_rate = data.get('risk_free_rate')
        
        # Validate budget
        try:
            budget = float(budget)
            if budget <= 0:
                return jsonify({'error': 'Budget must be a positive number'}), 400
        except (ValueError, TypeError):
            return jsonify({'error': 'Budget must be a valid number'}), 400
        
        # Validate risk-free rate
        try:
            risk_free_rate = float(risk_free_rate)
        except (ValueError, TypeError):
            return jsonify({'error': 'Risk-free rate must be a valid number'}), 400
        
        # Validate date range
        try:
            start_date, end_date = validate_date_range(start_date_str, end_date_str)
        except ValueError as e:
            return jsonify({'error': str(e)}), 400
        
        # Validate portfolio data structure
        if not isinstance(portfolio_data, dict):
            return jsonify({'error': 'Portfolio data must be an object'}), 400
        
        if 'weights' not in portfolio_data or 'prices' not in portfolio_data:
            return jsonify({
                'error': 'Portfolio data must contain "weights" and "prices" fields'
            }), 400
        
        # Calculate benchmark
        result = calculate_portfolio_benchmark(
            portfolio_data, 
            budget, 
            start_date, 
            end_date, 
            risk_free_rate
        )
        
        return jsonify(result), 200
        
    except ValueError as e:
        # Handle validation errors from calculation module
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        # Handle unexpected errors
        app.logger.error(f"Portfolio benchmarking failed: {str(e)}")
        return jsonify({
            'error': 'An internal error occurred while benchmarking the portfolio'
        }), 500

@app.route('/api/manage-portfolio', methods=['POST'])
def manage_portfolio_endpoint():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Request must be JSON'}), 400
            
        current_holdings = data.get('current_holdings', {})
        cash_injection = float(data.get('cash_injection', 0.0))
        start_date_str = data.get('start_date')
        end_date_str = data.get('end_date')
        risk_free_rate = float(data.get('risk_free_rate', 0.0))
        
        forecast_method = data.get('forecast_method', 'LIGHTWEIGHT')
        optimization_method = data.get('optimization_method', 'BL')
        ticker_group = data.get('ticker_group')
        
        target_return = data.get('target_return')
        risk_tolerance = data.get('risk_tolerance')
        forecast_horizon = int(data.get('forecast_horizon', 252))
        min_history = int(data.get('min_history', 100))
        bl_tau = float(data.get('bl_tau', 0.05))
        
        allow_fractional = bool(data.get('allow_fractional', True))
        fractional_overrides = data.get('fractional_overrides', {})
        tickers = data.get('tickers', None)

        try:
            start_date, end_date = validate_date_range(start_date_str, end_date_str)
        except ValueError as e:
            return jsonify({'error': str(e)}), 400

        result = manage_portfolio_logic(
            current_holdings=current_holdings,
            cash_injection=cash_injection,
            start_date=start_date,
            end_date=end_date,
            risk_free_rate=risk_free_rate,
            forecast_method=forecast_method,
            optimization_method=optimization_method,
            ticker_group=ticker_group,
            target_return=target_return,
            risk_tolerance=risk_tolerance,
            forecast_horizon=forecast_horizon,
            min_history=min_history,
            bl_tau=bl_tau,
            allow_fractional=allow_fractional,
            fractional_overrides=fractional_overrides,
            tickers=tickers
        )
        
        if "error" in result:
            return jsonify(result), 400
            
        return jsonify(result)
    except Exception as e:
        app.logger.error(f"manage_portfolio failed: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, threaded=True)
