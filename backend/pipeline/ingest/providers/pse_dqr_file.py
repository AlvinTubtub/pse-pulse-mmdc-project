"""Official PSE Daily Quotation Report (DQR) local file provider."""

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import logging
from pathlib import Path
import re
from typing import List, Optional

from backend.pipeline.ingest.base import EODMarketDataProvider
from backend.pipeline.ingest.models import EODQuote

logger = logging.getLogger(__name__)


class PSEDQRFileProvider(EODMarketDataProvider):
    """Parses official PSE Daily Quotation Reports supplied as local PDF or text files."""

    def __init__(self):
        self._last_seen_date: Optional[date] = None

    def load_quotes(
        self,
        source: Path,
        target_date: Optional[date] = None,
    ) -> List[EODQuote]:
        """Extract and normalize quotes from an official PSE DQR file."""
        source_path = Path(source)
        if not source_path.exists():
            raise FileNotFoundError(f"Source file does not exist: {source_path}")
        if not source_path.is_file():
            raise ValueError(f"Source path is not a file: {source_path}")

        raw_text = self._extract_text(source_path)
        if not raw_text.strip():
            raise ValueError(f"Extracted content is empty from {source_path.name}")

        trade_date = self._resolve_trade_date(raw_text, target_date, source_path.name)
        self._last_seen_date = trade_date

        quotes: List[EODQuote] = []
        for line in raw_text.splitlines():
            line_str = line.strip()
            if not line_str:
                continue
            quote = self._parse_line(line_str, trade_date, source_path.name)
            if quote:
                quotes.append(quote)

        logger.info(
            "Parsed %d quotes for trade date %s from %s",
            len(quotes),
            trade_date,
            source_path.name,
        )
        return quotes

    def _extract_text(self, path: Path) -> str:
        """Extract text content from PDF or plain text file."""
        if path.suffix.lower() == ".pdf":
            try:
                from pypdf import PdfReader

                reader = PdfReader(str(path))
                text_pages: List[str] = []
                for page in reader.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text_pages.append(page_text)
                return "\n".join(text_pages)
            except Exception as e:
                raise ValueError(f"Failed to extract text from PDF {path.name}: {e}") from e
        else:
            try:
                return path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                return path.read_text(encoding="latin-1")

    def _resolve_trade_date(
        self,
        text: str,
        target_date: Optional[date],
        filename: str,
    ) -> date:
        """Extract trade date from report header or validate against target_date."""
        extracted_date = self._find_date_in_text(text)

        if extracted_date and target_date:
            if extracted_date != target_date:
                raise ValueError(
                    f"Report date '{extracted_date}' in '{filename}' does not match requested target date '{target_date}'"
                )
            return target_date
        elif extracted_date:
            return extracted_date
        elif target_date:
            return target_date
        else:
            raise ValueError(
                f"Could not determine trade date from report header in '{filename}' and no target_date was specified"
            )

    def _find_date_in_text(self, text: str) -> Optional[date]:
        """Search text header for standard date formats."""
        # 1. Matches "October 1, 2026" or "October 01, 2026"
        month_pattern = (
            r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+"
            r"(\d{1,2}),\s+(\d{4})\b"
        )
        match = re.search(month_pattern, text, re.IGNORECASE)
        if match:
            month_str, day_str, year_str = match.groups()
            date_str = f"{month_str} {day_str} {year_str}"
            try:
                return datetime.strptime(date_str, "%B %d %Y").date()
            except ValueError:
                pass

        # 2. Matches ISO "2026-10-01"
        iso_match = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", text)
        if iso_match:
            try:
                return date.fromisoformat(iso_match.group(0))
            except ValueError:
                pass

        # 3. Matches "10/01/2026" or "10/1/2026"
        slash_match = re.search(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b", text)
        if slash_match:
            try:
                return datetime.strptime(slash_match.group(0), "%m/%d/%Y").date()
            except ValueError:
                pass

        return None

    def _parse_line(
        self,
        line: str,
        trade_date: date,
        filename: str,
    ) -> Optional[EODQuote]:
        """Attempt to parse an individual line as an equity quotation record."""
        # Split line by comma if CSV, otherwise by whitespace
        if "," in line and not re.search(r"\d,\d", line):
            tokens = [t.strip() for t in line.split(",") if t.strip()]
        else:
            # Handle quoted comma numbers by splitting whitespace while keeping comma numbers intact
            tokens = [t.strip() for t in re.split(r"\s+", line) if t.strip()]

        if len(tokens) < 7:
            return None

        # Ignore sector banner and header rows
        upper_tokens = [t.upper() for t in tokens]
        if any(h in upper_tokens for h in ["SYMBOL", "BID", "ASK", "OPEN", "HIGH", "LOW", "CLOSE", "VOLUME", "VALUE"]):
            return None
        if any(h in upper_tokens for h in ["SECTOR", "FINANCIALS", "PROPERTY", "INDUSTRIAL", "HOLDING", "SERVICES", "MINING"]):
            return None

        # Identify candidate symbol token (1 to 10 uppercase letters or numbers, e.g. SMPH, 2GO, BPI)
        # Often symbol is token 0 or token 1 (if token 0 is security code)
        symbol_idx = None
        for i in range(min(3, len(tokens) - 6)):
            cand = tokens[i].upper()
            if re.match(r"^[A-Z0-9]{1,10}$", cand) and not cand.replace(".", "").isdigit():
                symbol_idx = i
                break

        if symbol_idx is None:
            return None

        symbol = tokens[symbol_idx].upper()
        remainder = tokens[symbol_idx + 1 :]

        # Standard PSE DQR layouts:
        # Case A (9 numbers: Bid, Ask, Open, High, Low, Close, Volume, Value, [NetForeign])
        # Case B (7 numbers: Open, High, Low, Close, Volume, Value, [NetForeign])
        # Case C (6 numbers: Open, High, Low, Close, Volume, Value)
        # Clean numeric tokens:
        numeric_tokens = [self._clean_numeric(t) for t in remainder]
        non_none_count = sum(1 for x in numeric_tokens if x is not None)
        if non_none_count < 6:
            return None

        try:
            if len(numeric_tokens) >= 8 and numeric_tokens[2] is not None and numeric_tokens[3] is not None:
                # Layout: Bid (0), Ask (1), Open (2), High (3), Low (4), Close (5), Volume (6), Value (7)
                open_str = numeric_tokens[2]
                high_str = numeric_tokens[3]
                low_str = numeric_tokens[4]
                close_str = numeric_tokens[5]
                vol_str = numeric_tokens[6]
                val_str = numeric_tokens[7] if len(numeric_tokens) > 7 else None
                bid_str = numeric_tokens[0]
                ask_str = numeric_tokens[1]
            else:
                # Layout: Open (0), High (1), Low (2), Close (3), Volume (4), Value (5)
                open_str = numeric_tokens[0]
                high_str = numeric_tokens[1]
                low_str = numeric_tokens[2]
                close_str = numeric_tokens[3]
                vol_str = numeric_tokens[4]
                val_str = numeric_tokens[5] if len(numeric_tokens) > 5 else None
                bid_str = None
                ask_str = None

            if None in (open_str, high_str, low_str, close_str, vol_str):
                return None

            open_p = Decimal(open_str)
            high_p = Decimal(high_str)
            low_p = Decimal(low_str)
            close_p = Decimal(close_str)
            volume = int(Decimal(vol_str))

            val = Decimal(val_str) if val_str is not None else None
            bid_val = Decimal(bid_str) if bid_str is not None else None
            ask_val = Decimal(ask_str) if ask_str is not None else None

            return EODQuote(
                trade_date=trade_date,
                symbol=symbol,
                open_price=open_p,
                high_price=high_p,
                low_price=low_p,
                close_price=close_p,
                volume=volume,
                value=val,
                bid=bid_val,
                ask=ask_val,
                source="PSE_DQR_FILE",
                source_filename=filename,
            )
        except (InvalidOperation, ValueError, TypeError) as err:
            logger.debug("Failed parsing row for %s: %s", symbol, err)
            return None

    @staticmethod
    def _clean_numeric(token: str) -> Optional[str]:
        """Normalize numeric token: remove commas, PHP symbols, parenthesized negatives."""
        cleaned = token.strip()
        cleaned = re.sub(r"^[₱P(HP)]+", "", cleaned, flags=re.IGNORECASE)
        cleaned = cleaned.replace(",", "")

        # Check for empty / blank indicators
        if cleaned in ["-", "--", "N.A.", "N/A", "nil", ""]:
            return None

        # Parenthesized negative (1,234) -> -1234
        if cleaned.startswith("(") and cleaned.endswith(")"):
            cleaned = "-" + cleaned[1:-1].strip()

        # Check if valid numeric string
        try:
            # Test if Decimal can parse
            Decimal(cleaned)
            return cleaned
        except InvalidOperation:
            return None
