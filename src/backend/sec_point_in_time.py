"""SEC filing-date point-in-time fundamental feature construction."""

import hashlib
import json
import re
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests


SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_COMPANY_FACTS_URL = (
    "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
)
SEC_SUBMISSIONS_URL = (
    "https://data.sec.gov/submissions/CIK{cik:010d}.json"
)
ANNUAL_FORMS = {
    "10-K",
    "10-K/A",
    "20-F",
    "20-F/A",
    "40-F",
    "40-F/A",
}
QUARTERLY_FORMS = {"10-Q", "10-Q/A"}
PERIODIC_FORMS = ANNUAL_FORMS | QUARTERLY_FORMS
FLOW_CONCEPTS = (
    "net_income",
    "revenue",
    "gross_profit",
    "operating_cash_flow",
)

CONCEPTS = {
    "net_income": (
        ("us-gaap", "NetIncomeLoss", ("USD",)),
        (
            "us-gaap",
            "ProfitLoss",
            ("USD",),
        ),
        ("ifrs-full", "ProfitLoss", ("USD",)),
        (
            "ifrs-full",
            "ProfitLossAttributableToOwnersOfParent",
            ("USD",),
        ),
    ),
    "revenue": (
        (
            "us-gaap",
            "RevenueFromContractWithCustomerExcludingAssessedTax",
            ("USD",),
        ),
        ("us-gaap", "Revenues", ("USD",)),
        ("us-gaap", "SalesRevenueNet", ("USD",)),
        ("ifrs-full", "Revenue", ("USD",)),
        (
            "ifrs-full",
            "RevenueFromContractsWithCustomers",
            ("USD",),
        ),
    ),
    "gross_profit": (
        ("us-gaap", "GrossProfit", ("USD",)),
        ("ifrs-full", "GrossProfit", ("USD",)),
    ),
    "operating_cash_flow": (
        (
            "us-gaap",
            "NetCashProvidedByUsedInOperatingActivities",
            ("USD",),
        ),
        (
            "ifrs-full",
            "CashFlowsFromUsedInOperatingActivities",
            ("USD",),
        ),
    ),
    "assets": (
        ("us-gaap", "Assets", ("USD",)),
        ("ifrs-full", "Assets", ("USD",)),
    ),
    "current_assets": (
        ("us-gaap", "AssetsCurrent", ("USD",)),
        ("ifrs-full", "CurrentAssets", ("USD",)),
    ),
    "current_liabilities": (
        ("us-gaap", "LiabilitiesCurrent", ("USD",)),
        ("ifrs-full", "CurrentLiabilities", ("USD",)),
    ),
    "shares": (
        (
            "dei",
            "EntityCommonStockSharesOutstanding",
            ("shares",),
        ),
        (
            "us-gaap",
            "CommonStockSharesOutstanding",
            ("shares",),
        ),
        (
            "ifrs-full",
            "NumberOfSharesOutstanding",
            ("shares",),
        ),
    ),
    "weighted_average_shares": (
        (
            "us-gaap",
            "WeightedAverageNumberOfSharesOutstandingBasic",
            ("shares",),
        ),
        (
            "us-gaap",
            "WeightedAverageNumberOfDilutedSharesOutstanding",
            ("shares",),
        ),
        (
            "ifrs-full",
            "WeightedAverageNumberOfSharesOutstandingBasic",
            ("shares",),
        ),
    ),
}


def sic_sector(sic):
    """Map SEC SIC to a broad, stable sector used for factor neutralization."""
    try:
        sic = int(sic)
    except (TypeError, ValueError):
        return "Unknown"
    if 100 <= sic <= 999:
        return "Agriculture"
    if 1000 <= sic <= 1499:
        return "Mining"
    if 1500 <= sic <= 1799:
        return "Construction"
    if 2000 <= sic <= 3999:
        return "Manufacturing"
    if 4000 <= sic <= 4999:
        return "Transportation Utilities"
    if 5000 <= sic <= 5199:
        return "Wholesale"
    if 5200 <= sic <= 5999:
        return "Retail"
    if 6000 <= sic <= 6799:
        return "Finance Real Estate"
    if 7000 <= sic <= 8999:
        return "Services"
    if 9000 <= sic <= 9999:
        return "Public Administration"
    return "Unknown"


class SecEdgarClient:
    """Small cached SEC client that enforces declared access and rate limits."""

    def __init__(
        self,
        user_agent,
        cache_dir=".cache/sec",
        minimum_interval=0.12,
        timeout=30,
        session=None,
    ):
        user_agent = str(user_agent or "").strip()
        if len(user_agent) < 10 or (
            "@" not in user_agent and "http" not in user_agent.lower()
        ):
            raise ValueError(
                "SEC user_agent must identify the application and provide "
                "an email address or project URL"
            )
        self.user_agent = user_agent
        self.cache_dir = Path(cache_dir).expanduser().resolve()
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.minimum_interval = max(0.10, float(minimum_interval))
        self.timeout = max(1, int(timeout))
        self.session = session or requests.Session()
        self.session.headers.update(
            {
                "User-Agent": self.user_agent,
                "Accept-Encoding": "gzip, deflate",
            }
        )
        self._last_request_at = 0.0

    def _cache_path(self, url):
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
        return self.cache_dir / f"{digest}.json"

    def _get_json(self, url, refresh=False):
        cache_path = self._cache_path(url)
        if cache_path.exists() and not refresh:
            return json.loads(cache_path.read_text(encoding="utf-8"))

        elapsed = time.monotonic() - self._last_request_at
        if elapsed < self.minimum_interval:
            time.sleep(self.minimum_interval - elapsed)
        response = self.session.get(
            url,
            timeout=self.timeout,
            headers={"User-Agent": self.user_agent},
        )
        self._last_request_at = time.monotonic()
        response.raise_for_status()
        payload = response.json()
        temporary = cache_path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(payload, separators=(",", ":")),
            encoding="utf-8",
        )
        temporary.replace(cache_path)
        return payload

    def ticker_cik_map(self, refresh=False):
        payload = self._get_json(SEC_TICKERS_URL, refresh=refresh)
        return parse_ticker_cik_map(payload)

    def company_facts(self, cik, refresh=False):
        return self._get_json(
            SEC_COMPANY_FACTS_URL.format(cik=int(cik)),
            refresh=refresh,
        )

    def submissions(self, cik, refresh=False):
        return self._get_json(
            SEC_SUBMISSIONS_URL.format(cik=int(cik)),
            refresh=refresh,
        )


class SecCompanyFactsDirectoryClient:
    """Read an extracted official SEC companyfacts archive from local disk."""

    def __init__(
        self,
        companyfacts_dir,
        ticker_cik_map,
        submissions=None,
        submissions_dir=None,
        ticker_cik_history=None,
    ):
        self.source_description = (
            "local extracted SEC EDGAR companyfacts bulk archive"
        )
        self.companyfacts_dir = Path(companyfacts_dir).expanduser().resolve()
        if not self.companyfacts_dir.is_dir():
            raise ValueError(
                f"SEC companyfacts directory does not exist: "
                f"{self.companyfacts_dir}"
            )
        self._ticker_cik_map = {
            str(ticker).strip().upper(): int(cik)
            for ticker, cik in dict(ticker_cik_map or {}).items()
            if str(ticker).strip()
        }
        if not self._ticker_cik_map:
            raise ValueError("Local SEC client requires a ticker-to-CIK map")
        self._ticker_cik_history = (
            normalize_ticker_cik_history(ticker_cik_history)
            if ticker_cik_history is not None
            else {
                ticker: [{
                    "ticker": ticker,
                    "cik": cik,
                    "effective_start": None,
                    "effective_end": None,
                    "sector": None,
                }]
                for ticker, cik in self._ticker_cik_map.items()
            }
        )
        self._submissions = {
            int(cik): dict(payload)
            for cik, payload in dict(submissions or {}).items()
        }
        self.submissions_dir = (
            None
            if submissions_dir is None
            else Path(submissions_dir).expanduser().resolve()
        )
        if (
            self.submissions_dir is not None
            and not self.submissions_dir.is_dir()
        ):
            raise ValueError(
                f"SEC submissions directory does not exist: "
                f"{self.submissions_dir}"
            )

    def ticker_cik_map(self, refresh=False):
        del refresh
        return dict(self._ticker_cik_map)

    def ticker_cik_history(self, ticker):
        return [
            dict(record)
            for record in self._ticker_cik_history.get(
                str(ticker).strip().upper(),
                [],
            )
        ]

    def company_facts_path(self, cik):
        return self.companyfacts_dir / f"CIK{int(cik):010d}.json"

    def company_facts(self, cik, refresh=False):
        del refresh
        path = self.company_facts_path(cik)
        if not path.is_file():
            raise FileNotFoundError(
                f"SEC companyfacts file is missing for CIK {int(cik):010d}"
            )
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or int(payload.get("cik", -1)) != int(cik):
            raise ValueError(
                f"SEC companyfacts CIK mismatch in {path.name}"
            )
        return payload

    def submissions(self, cik, refresh=False):
        del refresh
        cik = int(cik)
        if cik in self._submissions:
            return dict(self._submissions[cik])
        if self.submissions_dir is None:
            return {}
        path = self.submissions_dir / f"CIK{cik:010d}.json"
        if not path.is_file():
            return {}
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or int(payload.get("cik", -1)) != cik:
            raise ValueError(
                f"SEC submissions CIK mismatch in {path.name}"
            )
        return payload


def normalize_ticker_cik_map(mapping):
    """Normalize mapping/dataset input and reject ambiguous ticker identities."""
    if isinstance(mapping, dict):
        rows = [
            {"ticker": ticker, "cik": cik}
            for ticker, cik in mapping.items()
        ]
    else:
        frame = pd.DataFrame(mapping).copy()
        cik_column = "cik" if "cik" in frame.columns else "cik_str"
        if "ticker" not in frame.columns or cik_column not in frame.columns:
            raise ValueError("Ticker-CIK data requires ticker and cik columns")
        rows = frame.rename(columns={cik_column: "cik"}).to_dict(
            orient="records"
        )

    normalized = {}
    for row in rows:
        ticker = str(row.get("ticker") or "").strip().upper()
        try:
            cik = int(row.get("cik"))
        except (TypeError, ValueError):
            continue
        if not ticker or cik <= 0:
            continue
        previous = normalized.get(ticker)
        if previous is not None and previous != cik:
            raise ValueError(
                f"Ticker-CIK data maps {ticker} to multiple CIKs"
            )
        normalized[ticker] = cik
    if not normalized:
        raise ValueError("Ticker-CIK data contains no valid mappings")
    return normalized


def normalize_ticker_cik_history(history):
    """Normalize dated ticker-to-issuer identities and reject overlap."""
    if isinstance(history, dict) and all(
        isinstance(records, (list, tuple))
        for records in history.values()
    ):
        rows = []
        for ticker, records in history.items():
            for record in records:
                rows.append({"ticker": ticker, **dict(record)})
        frame = pd.DataFrame(rows)
    else:
        frame = pd.DataFrame(history).copy()
    required = {"ticker", "cik"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(
            "Ticker-CIK history is missing required columns: "
            + ", ".join(missing)
        )
    for column in ("effective_start", "effective_end", "sector"):
        if column not in frame.columns:
            frame[column] = None
    frame["ticker"] = frame["ticker"].astype(str).str.strip().str.upper()
    frame["cik"] = pd.to_numeric(frame["cik"], errors="coerce")
    for column in ("effective_start", "effective_end"):
        frame[column] = pd.to_datetime(frame[column], errors="coerce")
    if (
        (frame["ticker"] == "").any()
        or frame["cik"].isna().any()
        or (frame["cik"] <= 0).any()
    ):
        raise ValueError("Ticker-CIK history contains invalid identities")
    invalid_interval = (
        frame["effective_start"].notna()
        & frame["effective_end"].notna()
        & (frame["effective_start"] > frame["effective_end"])
    )
    if invalid_interval.any():
        raise ValueError(
            "Ticker-CIK history contains an inverted effective interval"
        )

    result = {}
    for ticker, group in frame.groupby("ticker", sort=True):
        records = []
        previous_end = None
        ordered = group.sort_values(
            ["effective_start", "effective_end"],
            na_position="first",
        )
        for row in ordered.itertuples(index=False):
            start = (
                None
                if pd.isna(row.effective_start)
                else pd.Timestamp(row.effective_start)
            )
            end = (
                None
                if pd.isna(row.effective_end)
                else pd.Timestamp(row.effective_end)
            )
            if previous_end is None and records:
                raise ValueError(
                    f"Ticker-CIK history has an open interval before "
                    f"another identity for {ticker}"
                )
            if (
                previous_end is not None
                and start is not None
                and start <= previous_end
            ):
                raise ValueError(
                    f"Ticker-CIK history has overlapping identities for "
                    f"{ticker}"
                )
            records.append({
                "ticker": ticker,
                "cik": int(row.cik),
                "effective_start": start,
                "effective_end": end,
                "sector": (
                    None
                    if pd.isna(row.sector)
                    or not str(row.sector).strip()
                    else str(row.sector).strip()
                ),
            })
            previous_end = end
        result[ticker] = records
    if not result:
        raise ValueError("Ticker-CIK history contains no valid identities")
    return result


def extract_cik_from_filing_metadata(filings):
    """Extract the registrant CIK from Yahoo SEC filing metadata URLs."""
    exhibit_candidates = []
    for filing in filings or []:
        if not isinstance(filing, dict):
            continue
        edgar_url = str(filing.get("edgarUrl") or "")
        match = re.search(r"_([0-9]{1,10})(?:[/?#]|$)", edgar_url)
        if match:
            return int(match.group(1))
        for exhibit_url in dict(filing.get("exhibits") or {}).values():
            match = re.search(
                r"/sec-filings/0*([0-9]{1,10})/",
                str(exhibit_url),
            )
            if match:
                exhibit_candidates.append(int(match.group(1)))
    return exhibit_candidates[0] if exhibit_candidates else None


def parse_ticker_cik_map(payload):
    """Parse the SEC company_tickers payload into an uppercase ticker map."""
    mapping = {}
    rows = payload.values() if isinstance(payload, dict) else payload
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        ticker = str(row.get("ticker") or "").strip().upper()
        try:
            cik = int(row.get("cik_str"))
        except (TypeError, ValueError):
            continue
        if ticker:
            mapping[ticker] = cik
    return mapping


def _concept_entries(company_facts, concept_name):
    entries = []
    for taxonomy, tag, preferred_units in CONCEPTS[concept_name]:
        concept = (
            company_facts.get("facts", {})
            .get(taxonomy, {})
            .get(tag, {})
        )
        units = concept.get("units", {})
        for unit in preferred_units:
            for raw in units.get(unit, []):
                try:
                    value = float(raw.get("val"))
                except (TypeError, ValueError):
                    continue
                if not np.isfinite(value):
                    continue
                entry = {
                    **raw,
                    "val": value,
                    "taxonomy": taxonomy,
                    "tag": tag,
                    "unit": unit,
                }
                for key in ("filed", "start", "end"):
                    if entry.get(key):
                        entry[key] = pd.Timestamp(entry[key])
                entries.append(entry)
    return entries


def _duration_days(entry):
    start = entry.get("start")
    end = entry.get("end")
    if start is None or end is None:
        return None
    return int((pd.Timestamp(end) - pd.Timestamp(start)).days)


def _annual_entries(company_facts, concept_name):
    return [
        entry
        for entry in _concept_entries(company_facts, concept_name)
        if entry.get("form") in ANNUAL_FORMS
        and entry.get("filed") is not None
        and entry.get("end") is not None
        and _duration_days(entry) is not None
        and 250 <= _duration_days(entry) <= 450
    ]


def annual_filing_anchors(company_facts):
    """Return unique annual report accessions using filing date as availability."""
    anchors = {}
    for concept_name in ("net_income", "revenue", "operating_cash_flow"):
        for entry in _annual_entries(company_facts, concept_name):
            accession = str(entry.get("accn") or "").strip()
            if not accession:
                continue
            key = (accession, pd.Timestamp(entry["end"]))
            candidate = {
                "accn": accession,
                "filed": pd.Timestamp(entry["filed"]),
                "report_end": pd.Timestamp(entry["end"]),
                "report_start": pd.Timestamp(entry["start"]),
                "form": entry.get("form"),
            }
            previous = anchors.get(key)
            if previous is None or candidate["filed"] < previous["filed"]:
                anchors[key] = candidate
    return sorted(
        anchors.values(),
        key=lambda item: (item["filed"], item["report_end"], item["accn"]),
    )


def _periodic_entries(company_facts, concept_name):
    return [
        entry
        for entry in _concept_entries(company_facts, concept_name)
        if entry.get("form") in PERIODIC_FORMS
        and entry.get("filed") is not None
        and entry.get("start") is not None
        and entry.get("end") is not None
        and _duration_days(entry) is not None
        and 60 <= _duration_days(entry) <= 450
    ]


def periodic_filing_anchors(company_facts):
    """Return actual current-period 10-Q/10-K filing anchors."""
    grouped = {}
    for concept_name in (
        "net_income",
        "revenue",
        "operating_cash_flow",
    ):
        for entry in _periodic_entries(company_facts, concept_name):
            accession = str(entry.get("accn") or "").strip()
            if not accession:
                continue
            key = (
                accession,
                pd.Timestamp(entry["filed"]),
                str(entry.get("form") or ""),
            )
            report_end = pd.Timestamp(entry["end"])
            report_start = pd.Timestamp(entry["start"])
            previous = grouped.get(key)
            if previous is None or report_end > previous["report_end"]:
                grouped[key] = {
                    "accn": accession,
                    "filed": pd.Timestamp(entry["filed"]),
                    "report_end": report_end,
                    "report_start": report_start,
                    "form": entry.get("form"),
                }
            elif report_end == previous["report_end"]:
                previous["report_start"] = min(
                    previous["report_start"],
                    report_start,
                )
    return sorted(
        grouped.values(),
        key=lambda item: (
            item["filed"],
            item["report_end"],
            item["accn"],
        ),
    )


def _anchor_duration_entries(company_facts, concept_name, anchor):
    return [
        entry
        for entry in _concept_entries(company_facts, concept_name)
        if entry.get("accn") == anchor["accn"]
        and entry.get("form") == anchor["form"]
        and entry.get("filed") is not None
        and pd.Timestamp(entry["filed"]) <= anchor["filed"]
        and entry.get("start") is not None
        and entry.get("end") is not None
        and pd.Timestamp(entry["end"]) == anchor["report_end"]
        and _duration_days(entry) is not None
    ]


def _quarter_flow_value(
    company_facts,
    concept_name,
    anchor,
    quarter_history,
):
    entries = _anchor_duration_entries(
        company_facts,
        concept_name,
        anchor,
    )
    direct = [
        entry
        for entry in entries
        if 60 <= _duration_days(entry) <= 120
    ]
    if direct:
        selected = min(
            direct,
            key=lambda entry: abs(_duration_days(entry) - 91),
        )
        return float(selected["val"])

    if anchor["form"] in ANNUAL_FORMS:
        cumulative = [
            entry
            for entry in entries
            if 250 <= _duration_days(entry) <= 450
        ]
        selected = (
            None
            if not cumulative
            else min(
                cumulative,
                key=lambda entry: abs(_duration_days(entry) - 365),
            )
        )
    else:
        cumulative = [
            entry
            for entry in entries
            if 120 < _duration_days(entry) <= 300
        ]
        selected = (
            None
            if not cumulative
            else max(cumulative, key=_duration_days)
        )
    if selected is None:
        return None

    period_start = pd.Timestamp(selected["start"])
    period_end = pd.Timestamp(selected["end"])
    prior_quarters = [
        value
        for quarter_end, value in quarter_history.items()
        if period_start < quarter_end < period_end
    ]
    expected_prior_quarters = max(
        1,
        int(round(_duration_days(selected) / 91.0)) - 1,
    )
    if len(prior_quarters) < expected_prior_quarters:
        return None
    return float(selected["val"] - sum(prior_quarters))


def _trailing_four_quarters(quarter_history, report_end):
    eligible = sorted(
        (
            pd.Timestamp(quarter_end),
            float(value),
        )
        for quarter_end, value in quarter_history.items()
        if pd.Timestamp(quarter_end) <= pd.Timestamp(report_end)
        and np.isfinite(float(value))
    )
    if len(eligible) < 4:
        return None
    trailing = eligible[-4:]
    if trailing[-1][0] != pd.Timestamp(report_end):
        return None
    span = int((trailing[-1][0] - trailing[0][0]).days)
    if not 240 <= span <= 380:
        return None
    return float(sum(value for _, value in trailing))


def _seasonal_quarter_change(
    quarter_history,
    report_end,
    scale,
):
    """Return current-minus-prior-year quarter flow scaled by current assets."""
    report_end = pd.Timestamp(report_end)
    current = quarter_history.get(report_end)
    if current is None or not np.isfinite(float(current)):
        return np.nan
    prior = [
        (abs(int((report_end - pd.Timestamp(date)).days) - 365), value)
        for date, value in quarter_history.items()
        if 320 <= int((report_end - pd.Timestamp(date)).days) <= 410
        and np.isfinite(float(value))
    ]
    if not prior:
        return np.nan
    _, prior_value = min(prior, key=lambda item: item[0])
    return _safe_ratio(float(current) - float(prior_value), scale)


def _periodic_weighted_shares(company_facts, anchor):
    entries = _anchor_duration_entries(
        company_facts,
        "weighted_average_shares",
        anchor,
    )
    positive = [
        entry for entry in entries if float(entry["val"]) > 0
    ]
    if not positive:
        return None
    direct = [
        entry
        for entry in positive
        if 60 <= _duration_days(entry) <= 120
    ]
    selected = (
        min(
            direct,
            key=lambda entry: abs(_duration_days(entry) - 91),
        )
        if direct
        else max(positive, key=_duration_days)
    )
    return float(selected["val"])


def _select_fact(
    company_facts,
    concept_name,
    anchor,
    duration,
):
    entries = (
        _annual_entries(company_facts, concept_name)
        if duration
        else _concept_entries(company_facts, concept_name)
    )
    eligible = [
        entry
        for entry in entries
        if entry.get("filed") is not None
        and pd.Timestamp(entry["filed"]) <= anchor["filed"]
        and entry.get("end") is not None
        and pd.Timestamp(entry["end"]) <= anchor["report_end"]
    ]
    exact = [
        entry
        for entry in eligible
        if entry.get("accn") == anchor["accn"]
        and pd.Timestamp(entry["end"]) == anchor["report_end"]
    ]
    candidates = exact or eligible
    if not candidates:
        return None
    candidates.sort(
        key=lambda entry: (
            pd.Timestamp(entry["end"]),
            pd.Timestamp(entry["filed"]),
            bool(entry.get("accn") == anchor["accn"]),
        )
    )
    return candidates[-1]


def _safe_ratio(numerator, denominator):
    if numerator is None or denominator is None:
        return np.nan
    numerator = float(numerator)
    denominator = float(denominator)
    if not np.isfinite(numerator) or not np.isfinite(denominator):
        return np.nan
    if abs(denominator) <= 1e-12:
        return np.nan
    return float(numerator / denominator)


def _price_on_or_before(price_series, date):
    prices = pd.Series(price_series, dtype=float).copy()
    prices.index = pd.to_datetime(prices.index)
    prices = prices.sort_index().replace([np.inf, -np.inf], np.nan).dropna()
    eligible = prices.loc[prices.index <= pd.Timestamp(date)]
    if eligible.empty or float(eligible.iloc[-1]) <= 0:
        return None
    return float(eligible.iloc[-1])


def build_company_pit_features(
    ticker,
    company_facts,
    submissions,
    price_series,
    start_date=None,
    end_date=None,
    sector_override=None,
    include_cash_accrual_quality=False,
):
    """Build annual filing-date features for one company without future facts."""
    ticker = str(ticker).strip().upper()
    sector = (
        str(sector_override).strip()
        if sector_override is not None
        and str(sector_override).strip()
        else sic_sector(submissions.get("sic"))
    )
    rows = []
    for anchor in annual_filing_anchors(company_facts):
        available_date = anchor["filed"]
        if start_date and available_date < pd.Timestamp(start_date):
            continue
        if end_date and available_date > pd.Timestamp(end_date):
            continue

        selected = {
            "net_income": _select_fact(
                company_facts,
                "net_income",
                anchor,
                duration=True,
            ),
            "revenue": _select_fact(
                company_facts,
                "revenue",
                anchor,
                duration=True,
            ),
            "gross_profit": _select_fact(
                company_facts,
                "gross_profit",
                anchor,
                duration=True,
            ),
            "operating_cash_flow": _select_fact(
                company_facts,
                "operating_cash_flow",
                anchor,
                duration=True,
            ),
            "assets": _select_fact(
                company_facts,
                "assets",
                anchor,
                duration=False,
            ),
            "current_assets": _select_fact(
                company_facts,
                "current_assets",
                anchor,
                duration=False,
            ),
            "current_liabilities": _select_fact(
                company_facts,
                "current_liabilities",
                anchor,
                duration=False,
            ),
            "shares": _select_fact(
                company_facts,
                "shares",
                anchor,
                duration=False,
            ),
            "weighted_average_shares": _select_fact(
                company_facts,
                "weighted_average_shares",
                anchor,
                duration=True,
            ),
        }
        values = {
            name: None if entry is None else float(entry["val"])
            for name, entry in selected.items()
        }
        filing_price = _price_on_or_before(price_series, available_date)
        shares = values["shares"]
        if shares is None or shares <= 0:
            shares = values["weighted_average_shares"]
        market_cap = (
            None
            if filing_price is None
            or shares is None
            or shares <= 0
            else float(filing_price * shares)
        )
        assets = values["assets"]
        net_income = values["net_income"]
        operating_cash_flow = values["operating_cash_flow"]
        quality_numerator = (
            operating_cash_flow
            if operating_cash_flow is not None
            else net_income
        )
        quality = _safe_ratio(quality_numerator, assets)
        cash_accrual_quality = _safe_ratio(
            (
                operating_cash_flow - net_income
                if operating_cash_flow is not None
                and net_income is not None
                else None
            ),
            assets,
        )
        profitability = _safe_ratio(
            values["gross_profit"],
            values["revenue"],
        )
        if not np.isfinite(profitability):
            profitability = _safe_ratio(
                net_income,
                values["revenue"],
            )
        valuation = _safe_ratio(net_income, market_cap)
        liquidity = _safe_ratio(
            values["current_assets"],
            values["current_liabilities"],
        )
        if market_cap is None or market_cap <= 0:
            continue
        row = {
            "available_date": available_date,
            "ticker": ticker,
            "sector": sector,
            "market_cap": market_cap,
            "quality": quality,
            "profitability": profitability,
            "valuation": valuation,
            "liquidity": liquidity,
            "filing_accession": anchor["accn"],
            "filing_form": anchor["form"],
            "report_end": anchor["report_end"],
            "filing_price": filing_price,
            "shares_outstanding": shares,
        }
        if include_cash_accrual_quality:
            row["cash_accrual_quality"] = cash_accrual_quality
        rows.append(row)
    if not rows:
        feature_columns = [
            "available_date",
            "ticker",
            "sector",
            "market_cap",
            "quality",
            "profitability",
            "valuation",
            "liquidity",
        ]
        if include_cash_accrual_quality:
            feature_columns.append("cash_accrual_quality")
        return pd.DataFrame(
            columns=feature_columns
            + [
                "filing_accession",
                "filing_form",
                "report_end",
                "filing_price",
                "shares_outstanding",
            ]
        )
    return (
        pd.DataFrame(rows)
        .sort_values(["available_date", "ticker"])
        .drop_duplicates(["ticker", "available_date"], keep="last")
        .reset_index(drop=True)
    )


def build_company_quarterly_ttm_features(
    ticker,
    company_facts,
    submissions,
    price_series,
    start_date=None,
    end_date=None,
    sector_override=None,
    include_cash_accrual_quality=False,
    include_seasonal_earnings_change=False,
):
    """Build filing-date quarterly TTM features without future filings."""
    ticker = str(ticker).strip().upper()
    sector = (
        str(sector_override).strip()
        if sector_override is not None
        and str(sector_override).strip()
        else sic_sector(submissions.get("sic"))
    )
    quarter_history = {
        concept_name: {} for concept_name in FLOW_CONCEPTS
    }
    rows = []
    for anchor in periodic_filing_anchors(company_facts):
        for concept_name in FLOW_CONCEPTS:
            quarter_value = _quarter_flow_value(
                company_facts,
                concept_name,
                anchor,
                quarter_history[concept_name],
            )
            if quarter_value is not None and np.isfinite(quarter_value):
                quarter_history[concept_name][
                    anchor["report_end"]
                ] = float(quarter_value)

        available_date = anchor["filed"]
        if start_date and available_date < pd.Timestamp(start_date):
            continue
        if end_date and available_date > pd.Timestamp(end_date):
            continue

        trailing = {
            concept_name: _trailing_four_quarters(
                quarter_history[concept_name],
                anchor["report_end"],
            )
            for concept_name in FLOW_CONCEPTS
        }
        selected = {
            "assets": _select_fact(
                company_facts,
                "assets",
                anchor,
                duration=False,
            ),
            "current_assets": _select_fact(
                company_facts,
                "current_assets",
                anchor,
                duration=False,
            ),
            "current_liabilities": _select_fact(
                company_facts,
                "current_liabilities",
                anchor,
                duration=False,
            ),
            "shares": _select_fact(
                company_facts,
                "shares",
                anchor,
                duration=False,
            ),
        }
        values = {
            name: None if entry is None else float(entry["val"])
            for name, entry in selected.items()
        }
        filing_price = _price_on_or_before(price_series, available_date)
        shares = values["shares"]
        if shares is None or shares <= 0:
            shares = _periodic_weighted_shares(company_facts, anchor)
        market_cap = (
            None
            if filing_price is None
            or shares is None
            or shares <= 0
            else float(filing_price * shares)
        )
        assets = values["assets"]
        net_income = trailing["net_income"]
        quality_numerator = (
            trailing["operating_cash_flow"]
            if trailing["operating_cash_flow"] is not None
            else net_income
        )
        quality = _safe_ratio(quality_numerator, assets)
        cash_accrual_quality = _safe_ratio(
            (
                trailing["operating_cash_flow"] - net_income
                if trailing["operating_cash_flow"] is not None
                and net_income is not None
                else None
            ),
            assets,
        )
        seasonal_earnings_change = _seasonal_quarter_change(
            quarter_history["net_income"],
            anchor["report_end"],
            assets,
        )
        profitability = _safe_ratio(
            trailing["gross_profit"],
            trailing["revenue"],
        )
        if not np.isfinite(profitability):
            profitability = _safe_ratio(
                net_income,
                trailing["revenue"],
            )
        valuation = _safe_ratio(net_income, market_cap)
        liquidity = _safe_ratio(
            values["current_assets"],
            values["current_liabilities"],
        )
        if market_cap is None or market_cap <= 0:
            continue
        row_features = [
            quality,
            profitability,
            valuation,
            liquidity,
        ]
        if include_cash_accrual_quality:
            row_features.append(cash_accrual_quality)
        if include_seasonal_earnings_change:
            row_features.append(seasonal_earnings_change)
        if all(
            not np.isfinite(value)
            for value in row_features
        ):
            continue
        row = {
            "available_date": available_date,
            "ticker": ticker,
            "sector": sector,
            "market_cap": market_cap,
            "quality": quality,
            "profitability": profitability,
            "valuation": valuation,
            "liquidity": liquidity,
            "filing_accession": anchor["accn"],
            "filing_form": anchor["form"],
            "report_end": anchor["report_end"],
            "filing_price": filing_price,
            "shares_outstanding": shares,
        }
        if include_cash_accrual_quality:
            row["cash_accrual_quality"] = cash_accrual_quality
        if include_seasonal_earnings_change:
            row["seasonal_earnings_change"] = seasonal_earnings_change
        rows.append(row)
    if not rows:
        feature_columns = [
            "available_date",
            "ticker",
            "sector",
            "market_cap",
            "quality",
            "profitability",
            "valuation",
            "liquidity",
        ]
        if include_cash_accrual_quality:
            feature_columns.append("cash_accrual_quality")
        if include_seasonal_earnings_change:
            feature_columns.append("seasonal_earnings_change")
        return pd.DataFrame(
            columns=feature_columns
            + [
                "filing_accession",
                "filing_form",
                "report_end",
                "filing_price",
                "shares_outstanding",
            ]
        )
    return (
        pd.DataFrame(rows)
        .sort_values(["available_date", "ticker", "report_end"])
        .drop_duplicates(["ticker", "available_date"], keep="last")
        .reset_index(drop=True)
    )


def build_sec_pit_features(
    tickers,
    prices,
    client,
    start_date=None,
    end_date=None,
    refresh=False,
    filing_frequency="annual",
    include_cash_accrual_quality=False,
    include_seasonal_earnings_change=False,
):
    """Fetch SEC facts and construct a long-form PIT feature dataset."""
    prices = pd.DataFrame(prices).copy()
    prices.index = pd.to_datetime(prices.index)
    filing_frequency = str(filing_frequency).strip().lower()
    if filing_frequency not in {"annual", "quarterly-ttm"}:
        raise ValueError(
            "filing_frequency must be annual or quarterly-ttm"
        )
    if include_cash_accrual_quality and include_seasonal_earnings_change:
        raise ValueError("Extended SEC feature sets are mutually exclusive")
    if (
        include_seasonal_earnings_change
        and filing_frequency != "quarterly-ttm"
    ):
        raise ValueError(
            "seasonal earnings change requires quarterly-ttm filings"
        )
    ticker_map = client.ticker_cik_map(refresh=refresh)
    frames = []
    failures = {}
    metadata = {}
    for ticker in [str(value).strip().upper() for value in tickers]:
        identities = (
            client.ticker_cik_history(ticker)
            if hasattr(client, "ticker_cik_history")
            else []
        )
        if not identities:
            cik = ticker_map.get(ticker)
            identities = (
                []
                if cik is None
                else [{
                    "ticker": ticker,
                    "cik": int(cik),
                    "effective_start": None,
                    "effective_end": None,
                    "sector": None,
                }]
            )
        if not identities:
            failures[ticker] = "ticker_not_in_sec_mapping"
            continue
        if ticker not in prices.columns:
            failures[ticker] = "price_history_missing"
            continue
        ticker_frames = []
        identity_metadata = []
        identity_failures = []
        for identity in identities:
            cik = int(identity["cik"])
            identity_start = identity.get("effective_start")
            identity_end = identity.get("effective_end")
            bounded_start = max(
                [
                    pd.Timestamp(value)
                    for value in (start_date, identity_start)
                    if value is not None
                ],
                default=None,
            )
            bounded_end = min(
                [
                    pd.Timestamp(value)
                    for value in (end_date, identity_end)
                    if value is not None
                ],
                default=None,
            )
            if (
                bounded_start is not None
                and bounded_end is not None
                and bounded_start > bounded_end
            ):
                continue
            try:
                facts = client.company_facts(cik, refresh=refresh)
                submissions = client.submissions(cik, refresh=refresh)
                builder = (
                    build_company_pit_features
                    if filing_frequency == "annual"
                    else build_company_quarterly_ttm_features
                )
                frame = builder(
                    ticker,
                    facts,
                    submissions,
                    prices[ticker],
                    start_date=bounded_start,
                    end_date=bounded_end,
                    sector_override=identity.get("sector"),
                    include_cash_accrual_quality=(
                        include_cash_accrual_quality
                    ),
                    **(
                        {
                            "include_seasonal_earnings_change": (
                                include_seasonal_earnings_change
                            )
                        }
                        if filing_frequency == "quarterly-ttm"
                        else {}
                    ),
                )
                if not frame.empty:
                    ticker_frames.append(frame)
                identity_metadata.append({
                    "cik": cik,
                    "entity_name": facts.get("entityName"),
                    "effective_start": (
                        None
                        if identity_start is None
                        else pd.Timestamp(identity_start).strftime(
                            "%Y-%m-%d"
                        )
                    ),
                    "effective_end": (
                        None
                        if identity_end is None
                        else pd.Timestamp(identity_end).strftime("%Y-%m-%d")
                    ),
                    "sector": identity.get("sector"),
                    "sic": submissions.get("sic"),
                    "sic_description": submissions.get("sicDescription"),
                    "row_count": int(len(frame)),
                })
            except Exception as exc:
                identity_failures.append(
                    f"CIK{cik:010d} {type(exc).__name__}: {exc}"
                )
        if not ticker_frames:
            failures[ticker] = (
                "; ".join(identity_failures)
                if identity_failures
                else "no_usable_annual_filing_features"
            )
            continue
        ticker_frame = (
            pd.concat(ticker_frames, ignore_index=True)
            .sort_values(["available_date", "ticker"])
            .drop_duplicates(["ticker", "available_date"], keep="last")
        )
        frames.append(ticker_frame)
        metadata[ticker] = {
            "cik": int(identity_metadata[-1]["cik"]),
            "entity_name": identity_metadata[-1]["entity_name"],
            "sic": identity_metadata[-1]["sic"],
            "sic_description": identity_metadata[-1]["sic_description"],
            "row_count": int(len(ticker_frame)),
            "identities": identity_metadata,
            "identity_failures": identity_failures,
        }
    features = (
        pd.concat(frames, ignore_index=True)
        if frames
        else pd.DataFrame()
    )
    provenance = {
        "source": getattr(
            client,
            "source_description",
            "SEC EDGAR companyfacts and submissions APIs",
        ),
        "availability_policy": "SEC filing date; filed <= signal as-of date",
        "feature_policy": {
            "filing_frequency": filing_frequency,
            "feature_set": (
                "core-seasonal-earnings-change"
                if include_seasonal_earnings_change
                else (
                    "core-cash-accrual"
                    if include_cash_accrual_quality
                    else "core"
                )
            ),
            "quality": "operating_cash_flow/assets; net_income/assets fallback",
            "profitability": "gross_profit/revenue; net_margin fallback",
            "valuation": "net_income/(filing-date price * shares)",
            "liquidity": "current_assets/current_liabilities",
            "market_cap": "filing-date price * reported shares outstanding",
            "shares_fallback": (
                "annual weighted-average basic/diluted shares when an "
                "instant shares-outstanding fact is unavailable"
            ),
            **(
                {
                    "cash_accrual_quality": (
                        "(operating_cash_flow-net_income)/assets; "
                        "higher means less accrual-dependent earnings"
                    )
                }
                if include_cash_accrual_quality
                else {}
            ),
            **(
                {
                    "seasonal_earnings_change": (
                        "(current_quarter_net_income-"
                        "prior_year_same_quarter_net_income)/assets"
                    )
                }
                if include_seasonal_earnings_change
                else {}
            ),
        },
        "tickers_requested": [
            str(value).strip().upper() for value in tickers
        ],
        "tickers_completed": sorted(metadata),
        "company_metadata": metadata,
        "failures": failures,
    }
    return features, provenance
