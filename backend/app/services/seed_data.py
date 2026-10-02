"""Development and Demo Data Seeder for PSE Pulse.

Explicitly labels all generated records as demo/development data.
Does NOT import any Capstone artifacts, research datasets, or external credentials.
"""

from datetime import date, timedelta, datetime, timezone
import logging
from typing import List, Dict, Any
from sqlalchemy.orm import Session

from backend.app.models.sector import Sector
from backend.app.models.company import Company
from backend.app.models.price import DailyPrice
from backend.app.models.model_metadata import ModelMetadata
from backend.app.models.forecast import Forecast
from backend.app.models.pipeline_run import PipelineRun
from backend.app.forecasting.base import PriceHistoryItem
from backend.app.forecasting.registry import forecast_registry

logger = logging.getLogger(__name__)

SECTORS_DATA = [
    {"name": "Property", "code": "PROP", "description": "Real estate developers and REITs"},
    {"name": "Financials", "code": "FIN", "description": "Universal banks and financial institutions"},
    {"name": "Services", "code": "SVC", "description": "Telecommunications, media, and utilities"},
    {"name": "Holding Firms", "code": "HOLD", "description": "Diversified conglomerates"},
    {"name": "Industrial", "code": "IND", "description": "Manufacturing, energy, and food & beverage"},
    {"name": "Mining & Oil", "code": "MIN", "description": "Natural resource extraction and exploration"},
]

COMPANIES_DATA = [
    {"symbol": "SMPH", "name": "SM Prime Holdings, Inc.", "sector_code": "PROP", "base_price": 28.50},
    {"symbol": "BDO", "name": "BDO Unibank, Inc.", "sector_code": "FIN", "base_price": 142.00},
    {"symbol": "ALI", "name": "Ayala Land, Inc.", "sector_code": "PROP", "base_price": 31.25},
    {"symbol": "BPI", "name": "Bank of the Philippine Islands", "sector_code": "FIN", "base_price": 118.50},
    {"symbol": "TEL", "name": "PLDT Inc.", "sector_code": "SVC", "base_price": 1340.00},
    {"symbol": "ICT", "name": "International Container Terminal Services", "sector_code": "SVC", "base_price": 380.00},
    {"symbol": "AC", "name": "Ayala Corporation", "sector_code": "HOLD", "base_price": 630.00},
    {"symbol": "GLO", "name": "Globe Telecom, Inc.", "sector_code": "SVC", "base_price": 2100.00},
]

MODELS_DATA = [
    {
        "name": "Lag-Informed Regression",
        "code": "LAG_REGRESSION",
        "version": "0.1.0-stub",
        "description": "Multi-period price lag regression baseline for short-term price trend projection.",
    },
    {
        "name": "ARIMA",
        "code": "ARIMA",
        "version": "0.1.0-stub",
        "description": "Autoregressive Integrated Moving Average time-series model for stationarized returns.",
    },
    {
        "name": "LSTM",
        "code": "LSTM",
        "version": "0.1.0-stub",
        "description": "Long Short-Term Memory neural network sequential architecture stub.",
    },
]


def seed_database_if_empty(db: Session) -> None:
    """Seed initial development data if tables are unpopulated."""
    # 1. Seed Sectors
    sector_map: Dict[str, Sector] = {}
    for s_info in SECTORS_DATA:
        sector = db.query(Sector).filter(Sector.code == s_info["code"]).first()
        if not sector:
            sector = Sector(
                name=s_info["name"],
                code=s_info["code"],
                description=s_info["description"],
            )
            db.add(sector)
            db.flush()
        sector_map[s_info["code"]] = sector

    # 2. Seed Model Metadata
    model_map: Dict[str, ModelMetadata] = {}
    for m_info in MODELS_DATA:
        meta = db.query(ModelMetadata).filter(ModelMetadata.code == m_info["code"]).first()
        if not meta:
            meta = ModelMetadata(
                name=m_info["name"],
                code=m_info["code"],
                version=m_info["version"],
                description=m_info["description"],
                is_active=True,
            )
            db.add(meta)
            db.flush()
        model_map[m_info["code"]] = meta

    # 3. Seed Companies & Historical Prices
    today = date.today()
    business_days: List[date] = []
    cursor_day = today
    while len(business_days) < 20:
        cursor_day -= timedelta(days=1)
        if cursor_day.weekday() < 5:  # Monday to Friday
            business_days.append(cursor_day)
    business_days.reverse()

    for c_info in COMPANIES_DATA:
        company = db.query(Company).filter(Company.symbol == c_info["symbol"]).first()
        if not company:
            sector = sector_map.get(c_info["sector_code"])
            company = Company(
                symbol=c_info["symbol"],
                name=c_info["name"],
                sector_id=sector.id if sector else 1,
                is_active=True,
            )
            db.add(company)
            db.flush()

        # Seed 20 historical prices if none exist
        existing_prices = db.query(DailyPrice).filter(DailyPrice.company_id == company.id).count()
        if existing_prices == 0:
            base_p = c_info["base_price"]
            for idx, b_date in enumerate(business_days):
                # Deterministic synthetic movement for demo purposes
                variation = ((idx % 5) - 2) * 0.008 * base_p
                close_p = round(base_p + variation, 2)
                open_p = round(close_p * 0.995, 2)
                high_p = round(max(close_p, open_p) * 1.01, 2)
                low_p = round(min(close_p, open_p) * 0.99, 2)
                vol = 100000 + (idx * 15000)

                price_rec = DailyPrice(
                    company_id=company.id,
                    trade_date=b_date,
                    open_price=open_p,
                    high_price=high_p,
                    low_price=low_p,
                    close_price=close_p,
                    volume=vol,
                    value=round(close_p * vol, 2),
                )
                db.add(price_rec)

    db.commit()

    # 4. Ensure demo PipelineRun exists to link forecasts
    demo_run = db.query(PipelineRun).filter(PipelineRun.run_id == "demo-init-run-0001").first()
    if not demo_run:
        demo_run = PipelineRun(
            run_id="demo-init-run-0001",
            status="COMPLETED",
            started_at=datetime.now(timezone.utc) - timedelta(minutes=10),
            completed_at=datetime.now(timezone.utc) - timedelta(minutes=9),
            records_ingested=160,
            forecasts_generated=120,
            is_demo_run=True,
        )
        db.add(demo_run)
        db.flush()

    # 5. Generate Demo Forecasts for each company using the registered providers
    for c_info in COMPANIES_DATA:
        company = db.query(Company).filter(Company.symbol == c_info["symbol"]).first()
        if not company:
            continue

        prices = (
            db.query(DailyPrice)
            .filter(DailyPrice.company_id == company.id)
            .order_by(DailyPrice.trade_date.asc())
            .all()
        )

        history_items = [
            PriceHistoryItem(
                trade_date=p.trade_date,
                open_price=float(p.open_price),
                high_price=float(p.high_price),
                low_price=float(p.low_price),
                close_price=float(p.close_price),
                volume=p.volume,
            )
            for p in prices
        ]

        for code, model_meta in model_map.items():
            provider = forecast_registry.get(code)
            if not provider:
                continue

            predictions = provider.generate_forecast(company.symbol, history_items, horizon_days=5)
            for pred in predictions:
                existing_fc = (
                    db.query(Forecast)
                    .filter(
                        Forecast.company_id == company.id,
                        Forecast.model_id == model_meta.id,
                        Forecast.target_date == pred.target_date,
                        Forecast.pipeline_run_id == demo_run.id,
                    )
                    .first()
                )
                if not existing_fc:
                    fc = Forecast(
                        company_id=company.id,
                        model_id=model_meta.id,
                        pipeline_run_id=demo_run.id,
                        target_date=pred.target_date,
                        predicted_price=pred.predicted_price,
                        lower_bound=pred.lower_bound,
                        upper_bound=pred.upper_bound,
                        confidence_level=pred.confidence_level,
                        is_demo=True,
                    )
                    db.add(fc)

    db.commit()
    logger.info("Database seeding completed successfully.")
