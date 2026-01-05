from flask import Flask, jsonify, request
from flask_cors import CORS
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta
from sklearn.linear_model import LinearRegression
from hedge_analysis import analyze_hedge_relationship
from portfolio_benchmark import calculate_portfolio_benchmark

import lightgbm as lgb
import pandas as pd
import psutil
from financial_statement import get_financial_ratios, get_financial_statements
from portfolio_optimization import (
    optimize_portfolio,
    load_portfolio_result,
    list_saved_portfolios
)
from ticker_lists import get_ticker_group
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

def generate_regression_data(ticker="", start_date=None, end_date=None, future_days=0):
    try:
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
        X = df[feature_columns]
        y = df['Price_Change'].values  # Predict the change, not the absolute price
        
        # Fit LightGBM model
        model = lgb.LGBMRegressor(n_estimators=100, learning_rate=0.1, num_leaves=31, verbose=-1)
        model.fit(X, y)
        
        # Generate regression line based on predicted changes
        predicted_changes = model.predict(X)
        # The regression line is the cumulative sum of predicted changes, starting from the first close price
        regression_line = df['Close'].iloc[0] + np.cumsum(predicted_changes)
        
        # Convert to date:value format
        dates = df.index.strftime('%Y-%m-%d').tolist()
        original_data = {date: float(price) for date, price in zip(dates, df['Close'])}
        regression_data = {date: float(price) for date, price in zip(dates, regression_line)}
        
        # Get stock info
        info = stock.info
        company_name = info.get('longName', ticker)

        future_predictions = {}
        if future_days > 0 and not X.empty:
            last_known_price = df['Close'].iloc[-1]
            last_date = df.index[-1]
            
            # Use the last row of features as the starting point for future predictions
            last_features = df[feature_columns].iloc[-1:].copy()

            for i in range(future_days):
                # Predict the change for the next day
                predicted_change = model.predict(last_features)[0]
                
                # Calculate the new price
                next_price = last_known_price + predicted_change
                
                # Update features for the next iteration
                next_date = last_date + timedelta(days=i + 1)
                last_features['Time'] += 1
                last_features['Lag1'] = last_known_price
                
                # For MAs, we'd ideally re-calculate based on a rolling window of prices.
                # This is a simplification; for more accuracy, we'd append the new price and re-calculate.
                # For this implementation, we'll keep them constant from the last known value,
                # as re-calculating them properly requires a more complex setup.
                
                # Store prediction
                future_predictions[next_date.strftime('%Y-%m-%d')] = float(next_price)
                
                # Update last known price for the next prediction
                last_known_price = next_price
        
        return {
            'prices': original_data,
            'regression': regression_data,
            'future_predictions': future_predictions,
            'companyName': company_name,
            'slope': 'N/A',
            'intercept': 'N/A'
        }
        
    except Exception as e:
        print(f"Error generating regression data: {str(e)}")
        return {
            'prices': {},
            'regression': {},
            'companyName': ticker, 
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
            'regression': {},
            'future_predictions': {}
        }
        
    except Exception as e:
        print(f"Error fetching data: {str(e)}")
        return {'prices': {}, 'companyName': ticker, 'regression': {}, 'future_predictions': {}}
    

    
# API endpoint to send data to the frontend
@app.route('/get-data', methods=['GET', 'OPTIONS'])
def get_data():
    ticker = request.args.get('ticker', 'AAPL')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    include_regression = request.args.get('regression', 'false').lower() == 'true'
    future_days_str = request.args.get('future_days', '0')
    try:
        future_days = int(future_days_str)
        if future_days < 0:
            future_days = 0 # Prevent negative days
    except ValueError:
        future_days = 0 # Default to 0 if conversion fails

    if include_regression:
        data = generate_regression_data(ticker, start_date, end_date, future_days=future_days)
    else:
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
                progress_callback=progress_adapter
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
        'persist_result': persist_result, 'load_if_available': load_if_available
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

if __name__ == '__main__':
    app.run(debug=True, threaded=True)