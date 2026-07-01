import math
import re
import time
from numbers import Real

import pandas as pd
import yfinance as yf

STATEMENT_TYPES = ("income", "balance", "cash")
STATEMENT_FREQUENCIES = ("annual", "quarterly")
BASE_CURRENCY = "USD"
DIRECT_USD_QUOTE_CURRENCIES = {"AUD", "EUR", "GBP", "NZD"}
TICKER_SUFFIX_CURRENCIES = {
    ".KS": "KRW",
    ".KQ": "KRW",
    ".T": "JPY",
    ".HK": "HKD",
    ".L": "GBp",
    ".AX": "AUD",
    ".TO": "CAD",
    ".V": "CAD",
    ".PA": "EUR",
    ".DE": "EUR",
    ".F": "EUR",
    ".MI": "EUR",
    ".MC": "EUR",
    ".AS": "EUR",
    ".BR": "EUR",
    ".SW": "CHF",
    ".ST": "SEK",
    ".OL": "NOK",
    ".CO": "DKK",
    ".SS": "CNY",
    ".SZ": "CNY",
    ".TW": "TWD",
    ".SI": "SGD",
    ".BO": "INR",
    ".NS": "INR",
    ".SA": "BRL",
    ".MX": "MXN",
    ".JO": "ZAR",
}

TOTAL_SCORE_WEIGHT = 100
DECISION_THRESHOLDS = (
    (80, "STRONG BUY"),
    (65, "BUY"),
    (50, "HOLD"),
    (35, "REDUCE"),
    (0, "SELL"),
)

BENCHMARK_CACHE_TTL_SECONDS = 24 * 60 * 60
_BENCHMARK_TABLE_CACHE = {}
_PEER_BENCHMARK_CACHE = {}
_FX_RATE_CACHE = {}

BENCHMARK_FIELD_MAP = {
    "per": "P/E",
    "forward_pe": "Fwd P/E",
    "pbr": "P/B",
    "psr": "P/S",
    "peg": "PEG",
}

YFINANCE_PEER_FIELD_MAP = {
    "per": "trailingPE",
    "forward_pe": "forwardPE",
    "pbr": "priceToBook",
    "psr": "priceToSalesTrailing12Months",
    "peg": ("pegRatio", "trailingPegRatio"),
    "roe": "returnOnEquity",
    "roa": "returnOnAssets",
    "profit_margin": ("profitMargins", "profitMargin"),
    "operating_margin": "operatingMargins",
    "revenue_growth": "revenueGrowth",
    "earnings_growth": "earningsGrowth",
    "debt_to_equity": "debtToEquity",
    "current_ratio": "currentRatio",
    "quick_ratio": "quickRatio",
    "beta": "beta",
}

ALLOW_NEGATIVE_PEER_AVERAGE_METRICS = {
    "roe",
    "roa",
    "profit_margin",
    "operating_margin",
    "revenue_growth",
    "earnings_growth",
}

QUOTE_CURRENCY_FIELDS = (
    "currentPrice",
    "regularMarketPrice",
    "previousClose",
    "open",
    "dayLow",
    "dayHigh",
    "fiftyTwoWeekLow",
    "fiftyTwoWeekHigh",
    "marketCap",
    "enterpriseValue",
)

FINANCIAL_CURRENCY_FIELDS = (
    "trailingEps",
    "forwardEps",
    "bookValue",
    "revenuePerShare",
    "totalRevenue",
)

SECTOR_NAME_ALIASES = {
    "basic materials": "Basic Materials",
    "communication services": "Communication Services",
    "consumer cyclical": "Consumer Cyclical",
    "consumer defensive": "Consumer Defensive",
    "energy": "Energy",
    "financial": "Financial",
    "financial services": "Financial",
    "healthcare": "Healthcare",
    "industrials": "Industrials",
    "real estate": "Real Estate",
    "technology": "Technology",
    "utilities": "Utilities",
}

SECTOR_REPRESENTATIVE_TICKERS = {
    "Basic Materials": ["LIN", "SHW", "FCX", "ECL", "APD", "NEM", "NUE", "DOW", "DD", "MLM"],
    "Communication Services": ["GOOGL", "GOOG", "META", "NFLX", "TMUS", "DIS", "VZ", "T", "CMCSA", "CHTR"],
    "Consumer Cyclical": ["AMZN", "TSLA", "HD", "MCD", "BKNG", "LOW", "TJX", "NKE", "SBUX", "ORLY"],
    "Consumer Defensive": ["WMT", "COST", "PG", "KO", "PEP", "PM", "MDLZ", "CL", "MO", "TGT"],
    "Energy": ["XOM", "CVX", "COP", "SLB", "EOG", "MPC", "PSX", "VLO", "OXY", "KMI"],
    "Financial": ["BRK-B", "JPM", "V", "MA", "BAC", "WFC", "GS", "MS", "AXP", "C"],
    "Healthcare": ["LLY", "UNH", "JNJ", "ABBV", "MRK", "TMO", "ABT", "ISRG", "DHR", "PFE"],
    "Industrials": ["GE", "CAT", "RTX", "UBER", "BA", "HON", "UNP", "DE", "ETN", "ADP"],
    "Real Estate": ["PLD", "AMT", "EQIX", "WELL", "SPG", "O", "DLR", "PSA", "CCI", "CBRE"],
    "Technology": ["NVDA", "MSFT", "AAPL", "AVGO", "ORCL", "AMD", "CRM", "ADBE", "CSCO", "ACN"],
    "Utilities": ["NEE", "SO", "DUK", "CEG", "AEP", "SRE", "D", "PCG", "EXC", "XEL"],
}

INDUSTRY_REPRESENTATIVE_TICKERS = {
    "auto manufacturers": {
        "name": "Auto Manufacturers",
        "tickers": ["TSLA", "TM", "BYDDY", "RACE", "GM", "F", "HMC", "STLA", "VWAGY", "MBGYY"],
    },
    "banks diversified": {
        "name": "Banks - Diversified",
        "tickers": ["JPM", "BAC", "WFC", "C", "HSBC", "RY", "TD", "UBS", "DB", "BCS"],
    },
    "biotechnology": {
        "name": "Biotechnology",
        "tickers": ["AMGN", "GILD", "REGN", "VRTX", "MRNA", "BIIB", "ALNY", "ILMN", "BNTX", "INCY"],
    },
    "communication equipment": {
        "name": "Communication Equipment",
        "tickers": ["CSCO", "ANET", "MSI", "NOK", "ERIC", "JNPR", "UI", "CIEN", "LITE", "COMM"],
    },
    "consumer electronics": {
        "name": "Consumer Electronics",
        "tickers": ["AAPL", "SONY", "SSNLF", "PCRFY", "LPL", "GRMN", "SONO", "GPRO", "VZIO", "HEAR"],
    },
    "drug manufacturers general": {
        "name": "Drug Manufacturers - General",
        "tickers": ["LLY", "JNJ", "MRK", "NVO", "NVS", "AZN", "PFE", "SNY", "GSK", "BMY"],
    },
    "electronic components": {
        "name": "Electronic Components",
        "tickers": ["APH", "GLW", "TEL", "TDY", "TRMB", "FLEX", "SANM", "PLXS", "VSH", "CLS"],
    },
    "internet content information": {
        "name": "Internet Content & Information",
        "tickers": ["GOOGL", "META", "TCEHY", "BIDU", "SPOT", "RDDT", "PINS", "SNAP", "MTCH", "YELP"],
    },
    "oil gas integrated": {
        "name": "Oil & Gas Integrated",
        "tickers": ["XOM", "CVX", "SHEL", "TTE", "BP", "EQNR", "ENI", "PBR", "SU", "CNQ"],
    },
    "semiconductor equipment materials": {
        "name": "Semiconductor Equipment & Materials",
        "tickers": ["ASML", "AMAT", "LRCX", "KLAC", "TEL", "TER", "TOELY", "MKSI", "UCTT", "ACLS"],
    },
    "semiconductors": {
        "name": "Semiconductors",
        "tickers": ["NVDA", "TSM", "AVGO", "ASML", "AMD", "QCOM", "TXN", "AMAT", "MU", "INTC"],
    },
    "software application": {
        "name": "Software - Application",
        "tickers": ["CRM", "SAP", "INTU", "UBER", "SHOP", "ADSK", "NOW", "ADP", "WDAY", "TEAM"],
    },
    "software infrastructure": {
        "name": "Software - Infrastructure",
        "tickers": ["MSFT", "ORCL", "ADBE", "PLTR", "SNOW", "CRWD", "DDOG", "NET", "MDB", "ZS"],
    },
    "specialty industrial machinery": {
        "name": "Specialty Industrial Machinery",
        "tickers": ["GE", "HON", "ETN", "EMR", "ROK", "AME", "DOV", "XYL", "IR", "PH"],
    },
    "steel": {
        "name": "Steel",
        "tickers": ["NUE", "STLD", "MT", "PKX", "RS", "X", "CLF", "TX", "GGB", "SID"],
    },
    "telecom services": {
        "name": "Telecom Services",
        "tickers": ["TMUS", "VZ", "T", "CHT", "BCE", "TU", "TEF", "VOD", "ORAN", "SKM"],
    },
}


def _json_safe_value(value):
    if isinstance(value, Real) and math.isinf(value):
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


def _safe_number(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def _format_number(value, decimals=2):
    number = _safe_number(value)
    if number is None:
        return "N/A"
    return f"{number:.{decimals}f}"


def _format_percent(value, decimals=1):
    number = _safe_number(value)
    if number is None:
        return "N/A"
    return f"{number * 100:.{decimals}f}%"


def _format_market_cap(value):
    number = _safe_number(value)
    if number is None:
        return "N/A"
    abs_number = abs(number)
    if abs_number >= 1_000_000_000_000:
        return f"{number / 1_000_000_000_000:.2f}T"
    if abs_number >= 1_000_000_000:
        return f"{number / 1_000_000_000:.2f}B"
    if abs_number >= 1_000_000:
        return f"{number / 1_000_000:.2f}M"
    return f"{number:,.0f}"


def _normalize_currency(currency):
    if not currency:
        return None
    currency = str(currency).strip()
    if currency in {"GBp", "GBX"}:
        return "GBp"
    return currency.upper()


def _infer_currency_from_ticker(ticker_symbol):
    ticker_upper = str(ticker_symbol or "").upper()
    for suffix, currency in TICKER_SUFFIX_CURRENCIES.items():
        if ticker_upper.endswith(suffix):
            return currency
    return None


def _fx_spec_for_currency(currency):
    currency = _normalize_currency(currency)
    if not currency or currency == BASE_CURRENCY:
        return None
    if currency == "GBp":
        return "GBPUSD=X", "multiply", 0.01
    if currency in DIRECT_USD_QUOTE_CURRENCIES:
        return f"{currency}USD=X", "multiply", 1.0
    return f"{currency}=X", "divide", 1.0


def _extract_close_series(raw_data):
    if raw_data is None or raw_data.empty:
        return pd.Series(dtype=float)
    if isinstance(raw_data.columns, pd.MultiIndex):
        if "Close" in raw_data.columns.get_level_values(0):
            close_data = raw_data["Close"]
        else:
            close_data = raw_data
        if isinstance(close_data, pd.DataFrame):
            return close_data.iloc[:, 0]
        return close_data
    if "Close" in raw_data.columns:
        close_data = raw_data["Close"]
        if isinstance(close_data, pd.DataFrame):
            return close_data.iloc[:, 0]
        return close_data
    return raw_data.iloc[:, 0]


def _fetch_latest_usd_conversion_scalar(currency):
    currency = _normalize_currency(currency)
    spec = _fx_spec_for_currency(currency)
    if spec is None:
        return 1.0

    now = time.time()
    cached = _FX_RATE_CACHE.get(currency)
    if cached and now - cached["fetched_at"] < BENCHMARK_CACHE_TTL_SECONDS:
        return cached["value"]

    fx_ticker, operation, unit_multiplier = spec
    try:
        raw_fx_data = yf.download(fx_ticker, period="5d", progress=False, auto_adjust=True)
        fx_close = _extract_close_series(raw_fx_data).dropna()
        if fx_close.empty:
            return None

        latest_fx = _safe_number(fx_close.iloc[-1])
        if latest_fx is None or latest_fx <= 0:
            return None

        if operation == "multiply":
            factor = latest_fx * unit_multiplier
        else:
            factor = unit_multiplier / latest_fx

        _FX_RATE_CACHE[currency] = {
            "value": factor,
            "fetched_at": now,
        }
        return factor
    except Exception:
        return None


def _convert_currency_value(value, conversion_factor):
    number = _safe_number(value)
    factor = _safe_number(conversion_factor)
    if number is None or factor is None:
        return number
    return number * factor


def _first_positive(*values):
    for value in values:
        number = _safe_number(value)
        if number is not None and number > 0:
            return number
    return None


def _ratio_or_existing(numerator, denominator, existing):
    numerator = _safe_number(numerator)
    denominator = _safe_number(denominator)
    if numerator is not None and denominator is not None and numerator > 0 and denominator > 0:
        return numerator / denominator
    return _safe_number(existing)


def _financial_currency_context(info, ticker_symbol):
    quote_currency = _normalize_currency(info.get("currency")) or _infer_currency_from_ticker(ticker_symbol) or BASE_CURRENCY
    financial_currency = _normalize_currency(info.get("financialCurrency")) or quote_currency
    quote_factor = _fetch_latest_usd_conversion_scalar(quote_currency)
    financial_factor = _fetch_latest_usd_conversion_scalar(financial_currency)

    quote_conversion_available = quote_factor is not None
    financial_conversion_available = financial_factor is not None
    display_currency = BASE_CURRENCY if quote_conversion_available and financial_conversion_available else quote_currency

    return {
        "source_currency": quote_currency,
        "financial_currency": financial_currency,
        "display_currency": display_currency,
        "quote_to_usd": quote_factor,
        "financial_to_usd": financial_factor,
        "conversion_available": quote_conversion_available and financial_conversion_available,
    }


def _normalize_financial_info_to_usd(info, ticker_symbol):
    normalized = dict(info or {})
    currency_context = _financial_currency_context(normalized, ticker_symbol)

    quote_factor = currency_context["quote_to_usd"]
    financial_factor = currency_context["financial_to_usd"]
    if currency_context["conversion_available"]:
        for field in QUOTE_CURRENCY_FIELDS:
            if field in normalized:
                normalized[field] = _convert_currency_value(normalized.get(field), quote_factor)
        for field in FINANCIAL_CURRENCY_FIELDS:
            if field in normalized:
                normalized[field] = _convert_currency_value(normalized.get(field), financial_factor)

        price = _first_positive(normalized.get("currentPrice"), normalized.get("regularMarketPrice"))
        shares = _first_positive(normalized.get("sharesOutstanding"), normalized.get("impliedSharesOutstanding"))
        total_revenue = _first_positive(normalized.get("totalRevenue"))
        revenue_per_share = _first_positive(normalized.get("revenuePerShare"))

        if not revenue_per_share and total_revenue and shares:
            revenue_per_share = total_revenue / shares
            normalized["revenuePerShare"] = revenue_per_share

        normalized["trailingPE"] = _ratio_or_existing(price, normalized.get("trailingEps"), normalized.get("trailingPE"))
        normalized["forwardPE"] = _ratio_or_existing(price, normalized.get("forwardEps"), normalized.get("forwardPE"))
        normalized["priceToBook"] = _ratio_or_existing(price, normalized.get("bookValue"), normalized.get("priceToBook"))
        normalized["priceToSalesTrailing12Months"] = _ratio_or_existing(
            price,
            revenue_per_share,
            normalized.get("priceToSalesTrailing12Months"),
        )

        normalized["currency"] = BASE_CURRENCY
        normalized["financialCurrency"] = BASE_CURRENCY

    return normalized, currency_context


def _get_statement_frame(ticker, statement_type="income", frequency="annual"):
    if statement_type == "income":
        return ticker.quarterly_financials if frequency == "quarterly" else ticker.financials
    if statement_type == "balance":
        return ticker.quarterly_balance_sheet if frequency == "quarterly" else ticker.balance_sheet
    if statement_type == "cash":
        return ticker.quarterly_cashflow if frequency == "quarterly" else ticker.cashflow
    return None


def _statement_payload_from_frame(data):
    if data is None or data.empty:
        return None

    statement = data.copy()
    statement.columns = [
        col.strftime('%Y-%m-%d') if hasattr(col, 'strftime') else str(col)
        for col in statement.columns
    ]

    result = {
        "dates": list(statement.columns),
        "breakdown": []
    }

    for index, row in statement.iterrows():
        result["breakdown"].append({
            "row_label": index,
            "values": [_json_safe_value(value) for value in row.tolist()]
        })

    return result


def _calculate_debt_ratio(balance_sheet):
    if balance_sheet is None or balance_sheet.empty:
        return None

    latest_column = balance_sheet.columns[0]
    liabilities_labels = (
        "Total Liabilities Net Minority Interest",
        "Total Liabilities",
        "Total Liability",
    )
    assets_labels = ("Total Assets",)

    liabilities = None
    assets = None
    for label in liabilities_labels:
        if label in balance_sheet.index:
            liabilities = _safe_number(balance_sheet.loc[label, latest_column])
            break
    for label in assets_labels:
        if label in balance_sheet.index:
            assets = _safe_number(balance_sheet.loc[label, latest_column])
            break

    if liabilities is None or assets in (None, 0):
        return None
    return liabilities / assets


def _normalize_debt_to_equity(value):
    number = _safe_number(value)
    if number is None:
        return None
    # yfinance often returns this as percentage points, e.g. 98.5 for 0.985x.
    if abs(number) > 10:
        return number / 100
    return number


def _score_lower_better(value, good, fair, weak):
    number = _safe_number(value)
    if number is None:
        return None
    if number <= 0:
        return 0, "negative"
    if number <= good:
        return 100, "positive"
    if number <= fair:
        return 65, "neutral"
    if number <= weak:
        return 35, "caution"
    return 10, "negative"


def _score_higher_better(value, good, fair, weak):
    number = _safe_number(value)
    if number is None:
        return None
    if number >= good:
        return 100, "positive"
    if number >= fair:
        return 65, "neutral"
    if number >= weak:
        return 35, "caution"
    return 10, "negative"


def _score_current_ratio(value):
    number = _safe_number(value)
    if number is None:
        return None
    if 1.5 <= number <= 3:
        return 100, "positive"
    if 1 <= number < 1.5 or 3 < number <= 4:
        return 65, "neutral"
    if 0.75 <= number < 1 or 4 < number <= 6:
        return 35, "caution"
    return 10, "negative"


def _score_debt_ratio(value):
    number = _safe_number(value)
    if number is None:
        return None
    if number <= 0:
        return 0, "negative"
    if number <= 0.5:
        return 100, "positive"
    if number <= 0.75:
        return 65, "neutral"
    if number <= 1:
        return 35, "caution"
    return 10, "negative"


def _score_beta(value):
    number = _safe_number(value)
    if number is None:
        return None
    if 0.7 <= number <= 1.2:
        return 100, "positive"
    if 0 <= number < 0.7 or 1.2 < number <= 1.5:
        return 65, "neutral"
    if 1.5 < number <= 2:
        return 35, "caution"
    return 10, "negative"


def _benchmark_comparison(key, value, benchmarks, industry):
    benchmark = benchmarks.get(key) if benchmarks else None
    number = _safe_number(value)
    benchmark_value = _safe_number(benchmark.get("value")) if isinstance(benchmark, dict) else None

    if number is None or benchmark_value in (None, 0):
        return {
            "basis": "absolute_rule",
            "industry": industry,
            "industry_average": None,
            "status": "industry_average_unavailable",
        }

    difference = (number - benchmark_value) / abs(benchmark_value)
    if difference <= -0.05:
        position = "below"
    elif difference >= 0.05:
        position = "above"
    else:
        position = "near"

    return {
        "basis": benchmark.get("basis", "industry_average"),
        "industry": industry,
        "benchmark_name": benchmark.get("name"),
        "industry_average": benchmark_value,
        "industry_average_display": _format_number(benchmark_value),
        "relative_difference": difference,
        "relative_difference_display": _format_percent(difference),
        "position": position,
        "source": benchmark.get("source"),
        "sample_size": benchmark.get("sample_size"),
        "status": "available",
    }


def _metric(
    key,
    label,
    category,
    value,
    display_value,
    unit,
    weight,
    score_result,
    threshold_label,
    industry,
    benchmarks,
):
    if score_result is None:
        score = None
        signal = "missing"
    else:
        score, signal = score_result

    return {
        "key": key,
        "label": label,
        "category": category,
        "value": _safe_number(value),
        "display_value": display_value,
        "unit": unit,
        "weight": weight,
        "score": score,
        "signal": signal,
        "threshold": threshold_label,
        "comparison": _benchmark_comparison(key, value, benchmarks, industry),
    }


def _average(values, positive_only=True):
    cleaned = [_safe_number(value) for value in values]
    if positive_only:
        cleaned = [value for value in cleaned if value is not None and value > 0]
    else:
        cleaned = [value for value in cleaned if value is not None]
    if not cleaned:
        return None
    return sum(cleaned) / len(cleaned)


def _normalize_name(value):
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def _normalize_sector_name(sector):
    normalized = _normalize_name(sector)
    return SECTOR_NAME_ALIASES.get(normalized, sector)


def _load_finviz_group_table(group):
    from finvizfinance.group.valuation import Valuation

    return Valuation().screener_view(group=group, order="Name")


def _get_cached_finviz_group_table(group):
    now = time.time()
    cached = _BENCHMARK_TABLE_CACHE.get(group)
    if cached and now - cached["fetched_at"] < BENCHMARK_CACHE_TTL_SECONDS:
        return cached["data"]

    table = _load_finviz_group_table(group)
    _BENCHMARK_TABLE_CACHE[group] = {
        "data": table,
        "fetched_at": now,
    }
    return table


def _find_finviz_group_row(table, name):
    if table is None or table.empty or not name:
        return None

    normalized_name = _normalize_name(name)
    if not normalized_name:
        return None

    name_matches = table["Name"].map(_normalize_name) == normalized_name
    matches = table[name_matches]
    if matches.empty:
        return None
    return matches.iloc[0].to_dict()


def _benchmarks_from_finviz_row(row, basis, name):
    benchmarks = {}
    if not row:
        return benchmarks

    for metric_key, column in BENCHMARK_FIELD_MAP.items():
        value = _safe_number(row.get(column))
        if value is None or value <= 0:
            continue
        benchmarks[metric_key] = {
            "basis": basis,
            "name": name,
            "value": value,
            "source": "finvizfinance_group_valuation",
        }

    return benchmarks


def _fetch_finviz_group_benchmarks(info):
    industry = info.get("industry")
    sector = _normalize_sector_name(info.get("sector"))
    lookup_order = [
        ("Industry", industry, "industry_average"),
        ("Sector", sector, "sector_average"),
    ]

    for group, name, basis in lookup_order:
        if not name:
            continue
        try:
            table = _get_cached_finviz_group_table(group)
            row = _find_finviz_group_row(table, name)
            benchmarks = _benchmarks_from_finviz_row(row, basis, name)
        except Exception:
            benchmarks = {}
        if benchmarks:
            return benchmarks

    return {}


def _read_yfinance_peer_metric(metric_key, info, fields):
    field_names = fields if isinstance(fields, tuple) else (fields,)
    for field in field_names:
        value = _safe_number(info.get(field))
        if value is None:
            continue
        if metric_key == "debt_to_equity":
            value = _normalize_debt_to_equity(value)
            if value is None:
                continue
        if metric_key in ALLOW_NEGATIVE_PEER_AVERAGE_METRICS or value > 0:
            return value
    return None


def _representative_ticker_dataset(info):
    industry = _normalize_name(info.get("industry"))
    industry_dataset = INDUSTRY_REPRESENTATIVE_TICKERS.get(industry)
    if industry_dataset:
        return {
            "basis": "industry_representative_average",
            "name": f"{industry_dataset['name']} representative peers",
            "tickers": industry_dataset["tickers"],
            "cache_key": f"industry:{industry}",
        }

    sector = _normalize_sector_name(info.get("sector"))
    tickers = SECTOR_REPRESENTATIVE_TICKERS.get(sector)
    if not tickers:
        return None

    return {
        "basis": "sector_representative_average",
        "name": f"{sector} representative peers",
        "tickers": tickers,
        "cache_key": f"sector:{sector}",
    }


def _fetch_representative_peer_benchmarks(info, ticker_symbol):
    dataset = _representative_ticker_dataset(info)
    if not dataset:
        return {}

    now = time.time()
    cached = _PEER_BENCHMARK_CACHE.get(dataset["cache_key"])
    if cached and now - cached["fetched_at"] < BENCHMARK_CACHE_TTL_SECONDS:
        return cached["data"]

    current_symbol = str(ticker_symbol or "").upper()
    peer_tickers = [ticker for ticker in dataset["tickers"] if ticker.upper() != current_symbol] or dataset["tickers"]
    peer_values = {metric_key: [] for metric_key in YFINANCE_PEER_FIELD_MAP}

    for peer_ticker in peer_tickers[:10]:
        try:
            peer_info = yf.Ticker(peer_ticker).info or {}
        except Exception:
            continue
        if not isinstance(peer_info, dict):
            continue
        for metric_key, fields in YFINANCE_PEER_FIELD_MAP.items():
            value = _read_yfinance_peer_metric(metric_key, peer_info, fields)
            if value is not None:
                peer_values[metric_key].append(value)

    benchmarks = {}

    for metric_key, values in peer_values.items():
        average = _average(values, positive_only=metric_key not in ALLOW_NEGATIVE_PEER_AVERAGE_METRICS)
        if average is not None:
            benchmarks[metric_key] = {
                "basis": dataset["basis"],
                "name": dataset["name"],
                "value": average,
                "source": "yfinance_representative_peers",
                "sample_size": len(values),
            }

    if benchmarks:
        _PEER_BENCHMARK_CACHE[dataset["cache_key"]] = {
            "data": benchmarks,
            "fetched_at": now,
        }

    return benchmarks


def _fetch_financial_benchmarks(info, ticker_symbol):
    finviz_benchmarks = _fetch_finviz_group_benchmarks(info)
    representative_benchmarks = _fetch_representative_peer_benchmarks(info, ticker_symbol)
    if not finviz_benchmarks:
        return representative_benchmarks

    return {
        **representative_benchmarks,
        **finviz_benchmarks,
    }


def _build_investment_metrics(info, debt_ratio, benchmarks=None):
    industry = info.get("industry") or info.get("sector") or "N/A"
    pe_ratio = _safe_number(info.get("trailingPE"))
    forward_pe = _safe_number(info.get("forwardPE"))
    pb_ratio = _safe_number(info.get("priceToBook"))
    ps_ratio = _safe_number(info.get("priceToSalesTrailing12Months"))
    peg_ratio = _safe_number(info.get("pegRatio") or info.get("trailingPegRatio"))
    current_ratio = _safe_number(info.get("currentRatio"))
    quick_ratio = _safe_number(info.get("quickRatio"))
    debt_to_equity = _normalize_debt_to_equity(info.get("debtToEquity"))
    roe = _safe_number(info.get("returnOnEquity"))
    roa = _safe_number(info.get("returnOnAssets"))
    profit_margin = _safe_number(info.get("profitMargins") or info.get("profitMargin"))
    operating_margin = _safe_number(info.get("operatingMargins"))
    revenue_growth = _safe_number(info.get("revenueGrowth"))
    earnings_growth = _safe_number(info.get("earningsGrowth"))
    beta = _safe_number(info.get("beta"))

    return [
        _metric("per", "P/E", "valuation", pe_ratio, _format_number(pe_ratio), "ratio", 8,
                _score_lower_better(pe_ratio, 15, 25, 40), "<=15 attractive, 15-25 fair, >40 expensive", industry, benchmarks),
        _metric("forward_pe", "Forward P/E", "valuation", forward_pe, _format_number(forward_pe), "ratio", 6,
                _score_lower_better(forward_pe, 15, 25, 40), "<=15 attractive, 15-25 fair, >40 expensive", industry, benchmarks),
        _metric("pbr", "P/B", "valuation", pb_ratio, _format_number(pb_ratio), "ratio", 7,
                _score_lower_better(pb_ratio, 1.5, 3, 6), "<=1.5 attractive, 1.5-3 fair, >6 expensive", industry, benchmarks),
        _metric("psr", "P/S", "valuation", ps_ratio, _format_number(ps_ratio), "ratio", 5,
                _score_lower_better(ps_ratio, 2, 5, 10), "<=2 attractive, 2-5 fair, >10 expensive", industry, benchmarks),
        _metric("peg", "PEG", "valuation", peg_ratio, _format_number(peg_ratio), "ratio", 7,
                _score_lower_better(peg_ratio, 1, 2, 3), "<=1 attractive, 1-2 fair, >3 expensive", industry, benchmarks),
        _metric("roe", "ROE", "profitability", roe, _format_percent(roe), "percent", 9,
                _score_higher_better(roe, 0.15, 0.08, 0), ">=15% strong, 8-15% fair, <0% weak", industry, benchmarks),
        _metric("roa", "ROA", "profitability", roa, _format_percent(roa), "percent", 5,
                _score_higher_better(roa, 0.07, 0.03, 0), ">=7% strong, 3-7% fair, <0% weak", industry, benchmarks),
        _metric("profit_margin", "Profit Margin", "profitability", profit_margin, _format_percent(profit_margin), "percent", 8,
                _score_higher_better(profit_margin, 0.15, 0.05, 0), ">=15% strong, 5-15% fair, <0% weak", industry, benchmarks),
        _metric("operating_margin", "Operating Margin", "profitability", operating_margin, _format_percent(operating_margin), "percent", 5,
                _score_higher_better(operating_margin, 0.15, 0.05, 0), ">=15% strong, 5-15% fair, <0% weak", industry, benchmarks),
        _metric("revenue_growth", "Revenue Growth", "growth", revenue_growth, _format_percent(revenue_growth), "percent", 7,
                _score_higher_better(revenue_growth, 0.10, 0, -0.05), ">=10% strong, 0-10% fair, <-5% weak", industry, benchmarks),
        _metric("earnings_growth", "Earnings Growth", "growth", earnings_growth, _format_percent(earnings_growth), "percent", 7,
                _score_higher_better(earnings_growth, 0.10, 0, -0.05), ">=10% strong, 0-10% fair, <-5% weak", industry, benchmarks),
        _metric("debt_to_equity", "Debt/Equity", "stability", debt_to_equity, _format_number(debt_to_equity), "ratio", 7,
                _score_lower_better(debt_to_equity, 0.8, 1.5, 3), "<=0.8 conservative, 0.8-1.5 fair, >3 stretched", industry, benchmarks),
        _metric("debt_ratio", "Debt Ratio", "stability", debt_ratio, _format_number(debt_ratio), "ratio", 6,
                _score_debt_ratio(debt_ratio), "<=0.5 conservative, 0.5-0.75 fair, >1 stretched", industry, benchmarks),
        _metric("current_ratio", "Current Ratio", "stability", current_ratio, _format_number(current_ratio), "ratio", 5,
                _score_current_ratio(current_ratio), "1.5-3 healthy, <1 liquidity risk, >4 potential idle capital", industry, benchmarks),
        _metric("quick_ratio", "Quick Ratio", "stability", quick_ratio, _format_number(quick_ratio), "ratio", 4,
                _score_current_ratio(quick_ratio), "1.5-3 healthy, <1 liquidity risk, >4 potential idle capital", industry, benchmarks),
        _metric("beta", "Beta", "risk", beta, _format_number(beta), "ratio", 4,
                _score_beta(beta), "0.7-1.2 balanced, >1.5 volatile, <0 defensive", industry, benchmarks),
    ]


def _decision_from_score(score, confidence):
    if score is None or confidence < 20:
        return "INSUFFICIENT DATA"
    for minimum, label in DECISION_THRESHOLDS:
        if score >= minimum:
            return label
    return "SELL"


def _score_dashboard_metrics(metrics):
    available = [metric for metric in metrics if metric["score"] is not None]
    possible_weight = sum(metric["weight"] for metric in metrics)
    available_weight = sum(metric["weight"] for metric in available)

    if not available or not available_weight:
        return {
            "score": None,
            "max_score": TOTAL_SCORE_WEIGHT,
            "available_metrics": 0,
            "total_metrics": len(metrics),
            "confidence": 0,
            "label": "INSUFFICIENT DATA",
        }

    weighted_score = sum(metric["score"] * metric["weight"] for metric in available)
    score = round(weighted_score / available_weight)
    confidence = round((available_weight / possible_weight) * 100) if possible_weight else 0

    return {
        "score": score,
        "max_score": TOTAL_SCORE_WEIGHT,
        "available_metrics": len(available),
        "total_metrics": len(metrics),
        "confidence": confidence,
        "label": _decision_from_score(score, confidence),
    }


def _collect_all_statements(ticker):
    statements = {}
    errors = {}

    for frequency in STATEMENT_FREQUENCIES:
        statements[frequency] = {}
        errors[frequency] = {}

        for statement_type in STATEMENT_TYPES:
            try:
                frame = _get_statement_frame(ticker, statement_type, frequency)
                payload = _statement_payload_from_frame(frame)
                if payload is None:
                    statements[frequency][statement_type] = None
                    errors[frequency][statement_type] = f"No {frequency} {statement_type} statement data found."
                else:
                    statements[frequency][statement_type] = payload
            except Exception as exc:
                statements[frequency][statement_type] = None
                errors[frequency][statement_type] = str(exc)

    return statements, errors


def _legacy_ratios_from_metrics(ticker_symbol, info, metrics):
    by_key = {metric["key"]: metric for metric in metrics}
    return {
        "ticker": ticker_symbol,
        "longName": info.get('longName'),
        "per": by_key.get("per", {}).get("display_value", "N/A"),
        "pbr": by_key.get("pbr", {}).get("display_value", "N/A"),
        "psr": by_key.get("psr", {}).get("display_value", "N/A"),
        "debt_ratio": by_key.get("debt_ratio", {}).get("display_value", "N/A"),
        "liquidity_ratio": by_key.get("current_ratio", {}).get("display_value", "N/A"),
    }

def get_financial_ratios(ticker_symbol):
    """
    Fetches key financial ratios for a given stock ticker.

    Args:
        ticker_symbol (str): The stock ticker symbol (e.g., "MSFT").

    Returns:
        dict: A dictionary containing the financial ratios.
              Returns an error message in the 'error' key if data is unavailable.
    """
    try:
        ticker = yf.Ticker(ticker_symbol)
        info = ticker.info or {}
        info, _currency_context = _normalize_financial_info_to_usd(info, ticker_symbol)
        debt_ratio = _calculate_debt_ratio(ticker.balance_sheet)
        metrics = _build_investment_metrics(info, debt_ratio)
        return _legacy_ratios_from_metrics(ticker_symbol, info, metrics)

    except (KeyError, IndexError, TypeError) as e:
        return {"error": f"Could not retrieve all financial data for {ticker_symbol}. Some data might be unavailable."}


def get_financial_dashboard(ticker_symbol):
    """
    Fetches investment-oriented financial metrics plus full statement tables.
    The decision label is a rule-based analytical signal, not investment advice.
    """
    try:
        ticker = yf.Ticker(ticker_symbol)
        info = ticker.info or {}
        if not isinstance(info, dict):
            info = {}
        normalized_info, currency_context = _normalize_financial_info_to_usd(info, ticker_symbol)

        balance_sheet = _get_statement_frame(ticker, "balance", "annual")
        debt_ratio = _calculate_debt_ratio(balance_sheet)
        benchmarks = _fetch_financial_benchmarks(normalized_info, ticker_symbol)
        metrics = _build_investment_metrics(normalized_info, debt_ratio, benchmarks)
        decision = _score_dashboard_metrics(metrics)
        statements, statement_errors = _collect_all_statements(ticker)
        ratios = _legacy_ratios_from_metrics(ticker_symbol, normalized_info, metrics)
        display_currency = currency_context.get("display_currency") or normalized_info.get("currency") or "N/A"
        source_currency = currency_context.get("source_currency") or info.get("currency") or "N/A"
        financial_currency = currency_context.get("financial_currency") or info.get("financialCurrency") or source_currency

        return {
            **ratios,
            "company": {
                "ticker": ticker_symbol,
                "name": normalized_info.get("longName") or normalized_info.get("shortName") or ticker_symbol,
                "sector": normalized_info.get("sector") or "N/A",
                "industry": normalized_info.get("industry") or "N/A",
                "currency": display_currency,
                "display_currency": display_currency,
                "source_currency": source_currency,
                "financial_currency": financial_currency,
                "market_cap": _safe_number(normalized_info.get("marketCap")),
                "market_cap_display": _format_market_cap(normalized_info.get("marketCap")),
                "source_market_cap": _safe_number(info.get("marketCap")),
                "source_market_cap_display": _format_market_cap(info.get("marketCap")),
                "currency_conversion": {
                    "source_currency": source_currency,
                    "financial_currency": financial_currency,
                    "display_currency": display_currency,
                    "quote_to_usd": _safe_number(currency_context.get("quote_to_usd")),
                    "financial_to_usd": _safe_number(currency_context.get("financial_to_usd")),
                    "conversion_available": bool(currency_context.get("conversion_available")),
                },
            },
            "metrics": metrics,
            "decision": decision,
            "statements": statements,
            "statement_errors": statement_errors,
            "analysis_note": "Rule-based financial signal generated from available yfinance data. It is not investment advice.",
        }

    except Exception as e:
        return {"error": f"Error fetching financial dashboard: {str(e)}"}


def get_financial_statements(ticker_symbol, statement_type="income", frequency="annual"):
    """
    Fetches financial statements for a given stock ticker.

    Args:
        ticker_symbol (str): The stock ticker symbol.
        statement_type (str): "income", "balance", or "cash".
        frequency (str): "annual" or "quarterly".

    Returns:
        dict: A dictionary containing the financial statement data.
    """
    try:
        ticker = yf.Ticker(ticker_symbol)
        data = _get_statement_frame(ticker, statement_type, frequency)

        if data is None:
            return {"error": "Invalid statement type. Choose 'income', 'balance', or 'cash'."}

        if data is None or data.empty:
             return {"error": f"No {frequency} {statement_type} statement data found for {ticker_symbol}."}

        return _statement_payload_from_frame(data)

    except Exception as e:
        return {"error": f"Error fetching financial statements: {str(e)}"}

# Example usage:
if __name__ == '__main__':
    print("--- Running financial_statement.py script ---")
    # You can change this ticker symbol to test with others
    test_ticker = "AAPL"
    financial_data = get_financial_ratios(test_ticker)
    print(financial_data)

    test_ticker_2 = "GOOGL"
    financial_data_2 = get_financial_ratios(test_ticker_2)
    print(financial_data_2)
