# Product Tech Stack

## Frontend Framework & Build Tools
- **JavaScript Framework**: React 19.0.0
- **Build Tool**: Vite 6.1.0
- **Package Manager**: npm
- **Language**: JavaScript (ES6+)

## Backend Framework & Runtime
- **Application Framework**: Flask (Python)
- **CORS Handling**: Flask-CORS
- **Runtime**: Python 3.x
- **Package Manager**: pip

## Data Visualization & Charting
- **Charting Library**: Plotly.js 3.0.1 with React-Plotly.js 2.6.0
- **Interactive Visualizations**: Support for stock charts, regression plots, and future predictions

## Machine Learning & Data Science
- **Regression Models**: LightGBM (gradient boosting)
- **General ML**: scikit-learn (LinearRegression, statistical models)
- **Time Series Forecasting**: pmdarima
- **Data Manipulation**: pandas, numpy

## Financial Data & Analysis
- **Stock Data Source**: yfinance (Yahoo Finance API)
- **Portfolio Optimization**: PyPortfolioOpt (Modern Portfolio Theory, Efficient Frontier)
- **Financial Screening**: finvizfinance
- **System Monitoring**: psutil

## Internationalization
- **i18n Library**: i18next 25.0.2
- **React Integration**: react-i18next 15.5.1
- **Supported Languages**: English, Korean
- **Translation Management**: JSON-based locale files

## HTTP & API
- **HTTP Client**: Axios 1.8.4 (frontend)
- **API Communication**: RESTful API via Flask endpoints
- **Proxy Configuration**: Vite dev server proxy to Flask backend

## Code Quality & Development Tools
- **Linting**: ESLint 9.19.0
- **React Linting**: eslint-plugin-react, eslint-plugin-react-hooks
- **Development Server**: Vite dev server with HMR (Hot Module Replacement)

## Deployment & Hosting
- **Frontend Hosting**: Local development (port 5173)
- **Backend Hosting**: Local Flask server (port 5000)
- **Public Access**: ngrok tunneling for external access
- **Server Configuration**: Host 0.0.0.0 for network accessibility

## Database & Caching
- **Caching Strategy**: Custom Python cache manager
- **Data Storage**: In-memory caching for stock data, forecasts, and portfolio calculations
- **Cache Warming**: Pre-loading strategy for frequently accessed data

## Testing & Quality Assurance
- **Backend Testing**: pytest infrastructure (configured)
- **Error Handling**: Custom validation and error handling for date ranges and API responses
- **Data Validation**: Input sanitization for ticker symbols and date formats

## Third-Party Services
- **Stock Data Provider**: Yahoo Finance (via yfinance)
- **Financial Screening Data**: Finviz (via finvizfinance)

## Architecture Notes
- **Design Pattern**: Single Page Application (SPA) with React frontend
- **Backend Architecture**: Flask RESTful API with modular Python scripts
- **Communication**: Frontend-backend communication via HTTP REST API
- **Modularity**: Separated concerns (stock_screener.py, financial_statement.py, portfolio_optimization.py, hedge_analysis.py, forecast_models.py)
