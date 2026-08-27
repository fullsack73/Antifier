<div align="center">

# 📊 Antifier

**Intelligent Financial Analysis & Portfolio Optimization Platform**

[![License: CC BY-NC 4.0](https://img.shields.io/badge/License-CC%20BY--NC%204.0-lightgrey.svg)](LICENSE)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Node.js 16+](https://img.shields.io/badge/node-16+-green.svg)](https://nodejs.org/)
[![React 19](https://img.shields.io/badge/react-19-61dafb.svg)](https://reactjs.org/)
[![Flask](https://img.shields.io/badge/flask-3.1+-000000.svg)](https://flask.palletsprojects.com/)

[Features](#-features) • [Installation](#-installation) • [Usage](#-usage) • [Documentation](#-documentation) • [Contributing](#-contributing)

---

**Languages:** 🇺🇸 English | [🇰🇷 한국어](README.ko.md)

</div>

---

## 🎯 Overview

**Antifier** is a local React + Flask financial analysis webapp for stock research, predictive forecasting, financial statement review, screening, hedge analysis, portfolio optimization, benchmarking, and rebalancing.

The name "Antifier" comes from the Korean slang "ant," a nickname for small individual investors. Antifier is designed as an analysis support tool, not as investment advice or a return guarantee.

### Why Antifier?

- **🔄 One Connected Workflow**: Move from price charts and forecasts to financial ratios, screening, hedge checks, portfolio optimization, benchmarking, and rebalancing without switching tools
- **🤖 Forecast-Aware Modeling**: Compare LSTM, LightGBM, ARIMA, ARIMA + Transformer, Transformer, and lightweight forecast paths where they fit the workflow
- **📊 Financial Context**: Review company fundamentals with valuation, profitability, growth, stability, and risk metrics plus sector/industry benchmark context
- **🎯 Portfolio Lifecycle**: Optimize with MPT or Black-Litterman, export portfolio JSON, benchmark against S&P 500 and risk-free assets, then translate target weights into rebalance orders
- **🌐 Local, Bilingual App**: Run the React/Vite frontend and Flask API locally with English/Korean UI, `/api` proxy support, and installer/build tooling

---

## ✨ Features

### 📊 Stock Analysis & Forecasting
- Single-ticker historical price charts with configurable date ranges
- Regression and forecast model selection across LSTM, LightGBM, ARIMA, ARIMA + Transformer, and Transformer
- Future price forecast charts with configurable horizons and forecast ranges
- Currency metadata for prices when source and display currencies differ

### 📋 Financial Statements & Screening
- Financial dashboard with company summary, market cap, currency context, metric scores, and rule-based analysis signals
- Valuation, profitability, growth, stability, and risk metrics with industry/sector benchmark comparisons
- Finviz sector/industry valuation benchmarks with yfinance representative-peer fallbacks for missing metrics
- Stock screener for S&P 500, Dow Jones, or uploaded CSV ticker universes with multi-criteria financial filters and CSV export

### 💼 Portfolio Optimization
- Ledoit-Wolf global minimum variance as the production default, with opt-in MPT and Black-Litterman methods
- Modern Portfolio Theory and Black-Litterman optimization with forecast-based expected returns
- Forecast strategies for lightweight prediction, ARIMA + Transformer, and standalone Transformer
- Advanced controls for asset caps, L2 diversification, minimum holdings, turnover, ticker overrides, and sector/industry/country exposure bounds
- Pre-solver feasibility checks and structured constraint errors; current yfinance classifications are never presented as point-in-time historical metadata
- Progress streaming for long-running optimization jobs, downloadable portfolio JSON, return/risk/Sharpe summaries, risk contribution, concentration, covariance, metadata coverage, constraint slack, and weight tables
- Budget-to-shares allocation with global and per-ticker fractional-share controls

### 📈 Portfolio Benchmarking & Rebalancing
- Portfolio JSON upload and benchmark comparison against S&P 500 and a configurable risk-free asset
- Current-holdings portfolio manager with cash injection, target asset space selection, turnover controls, and rebalance order calculation
- Save/load portfolio inputs locally, export target holdings CSV, download portfolio JSON, and print/save rebalance results
- Hedge analysis for two tickers using correlation and regression over a selected date range

---

## 📋 Prerequisites

Before installing Antifier, ensure you have the following installed on your system:

- **Python 3.9+**: Required for backend processing and installer
  - Download from [python.org](https://www.python.org/downloads/)
  - Verify: `python --version` or `python3 --version`

- **Node.js 16+**: Required for frontend development server
  - Download from [nodejs.org](https://nodejs.org/)
  - Verify: `node --version`

These are required for both the one-click installer and manual installation methods.

---

## 🚀 Installation

### Option 1: One-Click Installer (Recommended)

Download the self-contained installer for your platform from [Releases](https://github.com/fullsack73/Antifier/releases):

**macOS:**
```bash
chmod +x antifier-installer-macos
./antifier-installer-macos
```

**Windows:**
```cmd
antifier-installer-windows.exe
```

**Linux:**
```bash
chmod +x antifier-installer-linux
./antifier-installer-linux
```

The installer automatically:
- Sets up Python virtual environment
- Installs all dependencies
- Configures the application
- Launches the webapp

### Option 2: Manual Installation

**Prerequisites:**
- Python 3.8 or higher
- Node.js 16 or higher
- npm or yarn

**Steps:**

1. **Clone the repository:**
```bash
git clone https://github.com/fullsack73/Antifier .
cd antifier
```

2. **Set up Python environment:**
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements-pypi.txt
```

3. **Install frontend dependencies:**
```bash
npm install
```

4. **Launch the application:**

**Terminal 1 - Backend:**
```bash
python src/backend/app.py
```

**Terminal 2 - Frontend:**
```bash
npm run dev
```

5. **Access the app:**
Open your browser to `http://localhost:5173`

---

## 📖 Usage

### Quick Start

1. **Select Stock Ticker**: Enter a stock symbol (e.g., AAPL, MSFT, GOOGL)
2. **Choose Date Range**: Select historical period for analysis
3. **View Analysis**: Explore charts, trends, and predictions
4. **Optimize Portfolio**: Add stocks to portfolio and run optimization
5. **Review Results**: Analyze efficient frontier and optimal allocations

---

## 🏗️ Architecture

### Technology Stack

**Frontend:**
- React 19 with Hooks
- Vite for build tooling
- Plotly.js for interactive charts
- i18next for internationalization
- Axios for API communication

**Backend:**
- Flask 3.1+ (Python web framework)
- Machine Learning: LightGBM/LSTM price regression, ARIMA + Transformer return forecasting, and lightweight fallback forecasting
- PyPortfolioOpt for Modern Portfolio Theory optimization
- Pandas for data manipulation
- NumPy/SciPy for numerical computation
- yfinance for stock data retrieval
- finvizfinance for Finviz sector/industry valuation benchmarks

**Build & Distribution:**
- PyInstaller for executable packaging
- GitHub Actions for CI/CD
- Multi-platform support (macOS, Windows, Linux)

### Project Structure

```
antifier/
├── src/
│   ├── backend/          # Flask API and ML models
│   │   ├── app.py        # Main Flask application
│   │   ├── forecast_models.py
│   │   ├── portfolio_optimization.py
│   │   └── stock_screener.py
│   └── frontend/         # React components
│       ├── App.jsx       # Main app component
│       ├── Optimizer.jsx
│       ├── StockChart.jsx
│       └── locales/      # i18n translations
├── tools/                # Build and installer scripts
│   ├── installer.py      # Self-contained installer
│   └── build-*.sh/bat    # Platform-specific builds
├── tests/                # Test suite
├── .github/workflows/    # CI/CD pipelines
└── requirements-pypi.txt # Python dependencies
```

---

## 📚 Documentation

- **Agent Workflow**: See [AGENTS.md](AGENTS.md)
- **Folder Architecture**: See [docs/01-folder-architecture.md](docs/01-folder-architecture.md)
- **Technical Specs**: See [docs/02-specs.md](docs/02-specs.md)
- **Product Plan**: See [docs/03-product-plan.md](docs/03-product-plan.md)
- **TODO Index**: See [docs/todo/00-todo-list.md](docs/todo/00-todo-list.md)
- **Work Reports**: See [docs/reports/](docs/reports/)
- **Build Instructions**: See [tools/BUILD.md](tools/BUILD.md)

---

## 🤝 Contributing

Any kind of contributions are welcome! Here's how you can help:

1. **Fork the repository**
2. **Create a feature branch**: `git checkout -b feature/amazing-feature`
3. **Commit your changes**: `git commit -m 'Add amazing feature'`
4. **Push to the branch**: `git push origin feature/amazing-feature`
5. **Open a Pull Request**

### Development Guidelines

- Follow existing code style and conventions
- Write tests for new features
- Update documentation as needed
- Ensure all tests pass before submitting PR

---

## 📄 License

This project is licensed under the **Creative Commons Attribution-NonCommercial 4.0 International License (CC BY-NC 4.0)**.

### You are free to:

- **Share** — copy and redistribute the material in any medium or format
- **Adapt** — remix, transform, and build upon the material

### Under the following terms:

- **Attribution** — You must give appropriate credit, provide a link to the license, and indicate if changes were made
- **NonCommercial** — You may not use the material for commercial purposes
- **No additional restrictions** — You may not apply legal terms or technological measures that legally restrict others from doing anything the license permits

### Important Notes:

- This software is provided for **personal, educational, and research purposes only**
- Commercial use, including but not limited to selling the software, using it in commercial services, or monetizing deployments, is **strictly prohibited** without explicit written permission
- You must comply with all third-party data provider terms of service (especially Yahoo Finance)

For the full license text, see the [LICENSE](LICENSE) file or visit:
https://creativecommons.org/licenses/by-nc/4.0/

---

## 🙏 Acknowledgments

- **Data Sources**: Financial data provided by [Yahoo Finance](https://finance.yahoo.com/)
- **Machine Learning**: Powered by [LightGBM](https://github.com/microsoft/LightGBM), ARIMA, Transformer models, and lightweight statistical forecasts
- **Optimization**: [PyPortfolioOpt](https://pypi.org/project/pyportfolioopt/) for Modern Portfolio Theory
- **Visualization**: Charts rendered with [Plotly.js](https://plotly.com/javascript/)

---

## ⚠️ Disclaimer

**This software is for educational and informational purposes only.**

Antifier is not a registered investment advisor and does not provide financial advice. The analysis, predictions, and recommendations generated by this software should not be considered as financial, investment, or trading advice. 

- Past performance does not guarantee future results
- All investment decisions carry risk of loss
- Always conduct your own research and consult with qualified financial professionals
- The developers and contributors are not liable for any financial losses

**Use at your own risk.**
