<div align="center">

# 📊 Antifier

**Intelligent Financial Analysis & Portfolio Optimization Platform**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Node.js 16+](https://img.shields.io/badge/node-16+-green.svg)](https://nodejs.org/)
[![React 19](https://img.shields.io/badge/react-19-61dafb.svg)](https://reactjs.org/)
[![Flask](https://img.shields.io/badge/flask-3.1+-000000.svg)](https://flask.palletsprojects.com/)

[Features](#-features) • [Installation](#-installation) • [Usage](#-usage) • [Documentation](#-documentation) • [Contributing](#-contributing)

</div>

---

## 🎯 Overview

**Antifier** is a comprehensive financial analysis webapp that helps investors and traders make data-driven investment decisions by automating quantitative stock analysis, predictive forecasting, and portfolio optimization.

### Why Antifier?

- **🔄 End-to-End Analysis**: From stock visualization to portfolio optimization in one integrated platform
- **🤖 Intelligent Automation**: Machine learning-powered forecasting and regression analysis
- **📈 Real-Time Insights**: Interactive charts with historical data and future predictions
- **🎯 Portfolio Optimization**: Modern Portfolio Theory implementation with efficient frontier analysis
- **⚡ Fast & Responsive**: React frontend with Flask backend for seamless performance

---

## ✨ Features

### 📊 Stock Analysis & Visualization
- Interactive historical stock price charts with customizable date ranges
- Multi-ticker comparison and analysis
- LightGBM-powered regression and trend analysis
- Future price predictions with configurable forecast periods

### 💼 Portfolio Management
- Portfolio optimization using Modern Portfolio Theory with ML-based return forecasting
- Automated model selection (ARIMA, LSTM, XGBoost) for expected returns prediction
- Efficient frontier calculation with optimal weight allocation
- Risk-return analysis with customizable parameters and constraints

### 🔍 Stock Screening & Filtering
- Custom financial metric filters (P/E, P/B, ROE, etc.)
- Pre-defined stock groups (S&P 500, Dow Jones, KOSPI 200)
- Multi-criteria screening for investment opportunities
- Financial statement analysis with key ratios

### 📉 Advanced Analysis Tools
- Portfolio benchmarking against S&P 500 and risk-free assets
- Hedge analysis and pairs trading strategies
- Statistical correlation and regression analysis
- Technical indicators and pattern recognition
- Risk-adjusted return calculations

---

## 🚀 Installation

### Option 1: One-Click Installer (Recommended)

Download the self-contained installer for your platform from [Releases](https://github.com/yourusername/antifier/releases):

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
git clone https://github.com/yourusername/antifier.git
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
- Machine Learning: LightGBM (regression), ARIMA, LSTM, XGBoost (forecasting)
- PyPortfolioOpt for Modern Portfolio Theory optimization
- Pandas for data manipulation
- NumPy/SciPy for numerical computation
- yfinance for stock data retrieval

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

- **User Guide**: See [docs/USER_GUIDE.md](docs/USER_GUIDE.md) *(coming soon)*
- **API Documentation**: See [docs/API.md](docs/API.md) *(coming soon)*
- **Build Instructions**: See [tools/BUILD.md](tools/BUILD.md)
- **Development Guide**: See [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) *(coming soon)*

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

This project is licensed under the **MIT License** - see the [LICENSE](LICENSE) file for details.

```
MIT License

Copyright (c) 2026 Antifier Contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

---

## 🙏 Acknowledgments

- **Data Sources**: Financial data provided by [Yahoo Finance](https://finance.yahoo.com/)
- **Machine Learning**: Powered by [LightGBM](https://github.com/microsoft/LightGBM), [XGBoost](https://xgboost.readthedocs.io/), ARIMA, and LSTM
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
