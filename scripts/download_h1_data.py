#!/usr/bin/env python3
"""
Download H1 (Hourly) OHLCV data for all trading assets.

Primary source: OANDA API
Fallback source: Yahoo Finance

Date range: 2014-01-01 to 2025-12-31
"""

import os
import sys
import time
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Tuple

import pandas as pd
from dotenv import load_dotenv
from tqdm import tqdm

# Load environment variables
load_dotenv()

# ═══════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════

ASSETS = [
    # Forex Majors (7)
    'EUR_USD', 'GBP_USD', 'USD_JPY', 'USD_CHF', 'AUD_USD', 'USD_CAD', 'NZD_USD',
    
    # Forex Crosses (21)
    'EUR_GBP', 'EUR_JPY', 'EUR_CHF', 'EUR_AUD', 'EUR_CAD', 'EUR_NZD',
    'GBP_JPY', 'GBP_CHF', 'GBP_AUD', 'GBP_CAD', 'GBP_NZD',
    'AUD_JPY', 'AUD_CHF', 'AUD_CAD', 'AUD_NZD',
    'NZD_JPY', 'NZD_CHF', 'NZD_CAD',
    'CHF_JPY', 'CAD_JPY', 'CAD_CHF',
    
    # Metals (2)
    'XAU_USD', 'XAG_USD',
    
    # Indices (2)
    'SPX500_USD', 'NAS100_USD',
    
    # Crypto (2)
    'BTC_USD', 'ETH_USD',
]

# Yahoo Finance symbol mapping (for fallback)
YAHOO_SYMBOL_MAP = {
    # Forex
    'EUR_USD': 'EURUSD=X',
    'GBP_USD': 'GBPUSD=X',
    'USD_JPY': 'USDJPY=X',
    'USD_CHF': 'USDCHF=X',
    'AUD_USD': 'AUDUSD=X',
    'USD_CAD': 'USDCAD=X',
    'NZD_USD': 'NZDUSD=X',
    'EUR_GBP': 'EURGBP=X',
    'EUR_JPY': 'EURJPY=X',
    'EUR_CHF': 'EURCHF=X',
    'EUR_AUD': 'EURAUD=X',
    'EUR_CAD': 'EURCAD=X',
    'EUR_NZD': 'EURNZD=X',
    'GBP_JPY': 'GBPJPY=X',
    'GBP_CHF': 'GBPCHF=X',
    'GBP_AUD': 'GBPAUD=X',
    'GBP_CAD': 'GBPCAD=X',
    'GBP_NZD': 'GBPNZD=X',
    'AUD_JPY': 'AUDJPY=X',
    'AUD_CHF': 'AUDCHF=X',
    'AUD_CAD': 'AUDCAD=X',
    'AUD_NZD': 'AUDNZD=X',
    'NZD_JPY': 'NZDJPY=X',
    'NZD_CHF': 'NZDCHF=X',
    'NZD_CAD': 'NZDCAD=X',
    'CHF_JPY': 'CHFJPY=X',
    'CAD_JPY': 'CADJPY=X',
    'CAD_CHF': 'CADCHF=X',
    
    # Metals
    'XAU_USD': 'GC=F',      # Gold Futures
    'XAG_USD': 'SI=F',      # Silver Futures
    
    # Indices
    'SPX500_USD': '^GSPC',  # S&P 500
    'NAS100_USD': '^NDX',   # Nasdaq 100
    
    # Crypto
    'BTC_USD': 'BTC-USD',
    'ETH_USD': 'ETH-USD',
}

DATA_DIR = Path('data/ohlcv')
START_DATE = '2014-01-01'
END_DATE = '2025-12-31'


# ═══════════════════════════════════════════════════════════════════════════
# OANDA API DOWNLOADER
# ═══════════════════════════════════════════════════════════════════════════

class OandaDownloader:
    """Download H1 data from OANDA API."""
    
    def __init__(self):
        self.account_id = os.getenv('OANDA_ACCOUNT_ID')
        self.api_key = os.getenv('OANDA_API_KEY')
        self.environment = os.getenv('OANDA_ENVIRONMENT', 'practice')
        
        if not self.account_id or not self.api_key:
            raise ValueError("OANDA credentials not found in .env")
        
        # Import oandapyV20
        try:
            import oandapyV20
            from oandapyV20.endpoints.instruments import InstrumentsCandles
            self.oandapyV20 = oandapyV20
            self.InstrumentsCandles = InstrumentsCandles
        except ImportError:
            raise ImportError("Install oandapyV20: pip install oandapyV20")
        
        # Create API client
        if self.environment == 'live':
            self.client = oandapyV20.API(access_token=self.api_key, environment="live")
        else:
            self.client = oandapyV20.API(access_token=self.api_key, environment="practice")
        
        print(f"✅ OANDA client initialized ({self.environment})")
    
    def download_candles(
        self,
        instrument: str,
        granularity: str = 'H1',
        start: str = None,
        end: str = None,
        count: int = 5000,
    ) -> Optional[pd.DataFrame]:
        """
        Download candles for an instrument.
        
        Args:
            instrument: OANDA instrument name (e.g., 'EUR_USD')
            granularity: Timeframe ('H1', 'D', etc.)
            start: Start datetime ISO format
            end: End datetime ISO format
            count: Max candles per request (max 5000)
        
        Returns:
            DataFrame with OHLCV data or None on error
        """
        params = {
            'granularity': granularity,
        }
        
        # OANDA doesn't allow count with from/to together
        if start and end:
            params['from'] = start
            params['to'] = end
        elif start:
            params['from'] = start
            params['count'] = count
        elif end:
            params['to'] = end
            params['count'] = count
        else:
            params['count'] = count
        
        try:
            request = self.InstrumentsCandles(instrument=instrument, params=params)
            response = self.client.request(request)
            
            candles = response.get('candles', [])
            if not candles:
                return None
            
            # Parse candles
            data = []
            for candle in candles:
                if candle.get('complete', True):  # Only complete candles
                    mid = candle.get('mid', {})
                    data.append({
                        'timestamp': candle['time'],
                        'open': float(mid.get('o', 0)),
                        'high': float(mid.get('h', 0)),
                        'low': float(mid.get('l', 0)),
                        'close': float(mid.get('c', 0)),
                        'volume': int(candle.get('volume', 0)),
                    })
            
            if not data:
                return None
            
            df = pd.DataFrame(data)
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            
            # Remove timezone info to make it naive
            if df['timestamp'].dt.tz is not None:
                df['timestamp'] = df['timestamp'].dt.tz_localize(None)
            
            return df
            
        except Exception as e:
            print(f"   ⚠️ OANDA error for {instrument}: {e}")
            return None
    
    def download_full_history(
        self,
        instrument: str,
        granularity: str = 'H1',
        start_date: str = '2014-01-01',
        end_date: str = '2025-12-31',
    ) -> Optional[pd.DataFrame]:
        """
        Download full history by chunking requests.
        
        OANDA limits to 5000 candles per request.
        H1 = 5000 hours ≈ 208 days per request.
        """
        print(f"   📥 Downloading {instrument} {granularity} from OANDA...")
        
        all_data = []
        current_start = datetime.fromisoformat(start_date)
        end_dt = datetime.fromisoformat(end_date)
        
        # Calculate chunk size (for H1, ~200 days per chunk to be safe)
        if granularity == 'H1':
            chunk_days = 180
        elif granularity == 'H4':
            chunk_days = 700
        else:
            chunk_days = 1800
        
        request_count = 0
        max_requests = 100  # Safety limit
        
        while current_start < end_dt and request_count < max_requests:
            chunk_end = min(current_start + timedelta(days=chunk_days), end_dt)
            
            df = self.download_candles(
                instrument=instrument,
                granularity=granularity,
                start=current_start.isoformat() + 'Z',
                end=chunk_end.isoformat() + 'Z',
                count=5000,
            )
            
            if df is not None and len(df) > 0:
                all_data.append(df)
                # Move to next chunk (use last timestamp + 1 hour to avoid overlap)
                last_ts = df['timestamp'].max()
                # Remove timezone info if present for comparison
                if hasattr(last_ts, 'tz_localize'):
                    last_ts = last_ts.tz_localize(None) if last_ts.tz is not None else last_ts
                current_start = last_ts + timedelta(hours=1)
            else:
                # No data, move forward anyway
                current_start = chunk_end
            
            request_count += 1
            
            # Rate limiting (OANDA allows ~30 requests/second for practice)
            time.sleep(0.1)
        
        if not all_data:
            return None
        
        # Combine all chunks
        result = pd.concat(all_data, ignore_index=True)
        
        # Remove duplicates (by timestamp)
        result = result.drop_duplicates(subset=['timestamp'], keep='last')
        result = result.sort_values('timestamp').reset_index(drop=True)
        
        print(f"   ✅ Downloaded {len(result):,} candles for {instrument}")
        
        return result


# ═══════════════════════════════════════════════════════════════════════════
# YAHOO FINANCE DOWNLOADER (Fallback)
# ═══════════════════════════════════════════════════════════════════════════

class YahooDownloader:
    """Download H1 data from Yahoo Finance (fallback)."""
    
    def __init__(self):
        try:
            import yfinance as yf
            self.yf = yf
        except ImportError:
            raise ImportError("Install yfinance: pip install yfinance")
        
        print("✅ Yahoo Finance client initialized")
    
    def download_candles(
        self,
        symbol: str,
        yahoo_symbol: str,
        start_date: str = '2014-01-01',
        end_date: str = '2025-12-31',
        interval: str = '1h',
    ) -> Optional[pd.DataFrame]:
        """
        Download hourly data from Yahoo Finance.
        
        Note: Yahoo Finance limits hourly data to last 730 days!
        For older data, we may need to use daily and interpolate.
        """
        print(f"   📥 Downloading {symbol} from Yahoo Finance...")
        
        try:
            # Yahoo Finance has limitations on hourly data
            # It only provides ~730 days of hourly data
            # For older data, we download what we can
            
            ticker = self.yf.Ticker(yahoo_symbol)
            
            # Try hourly first (limited history)
            df = ticker.history(
                start=start_date,
                end=end_date,
                interval=interval,
            )
            
            if df is None or len(df) == 0:
                print(f"   ⚠️ No hourly data for {symbol}, trying daily...")
                # Fallback to daily
                df = ticker.history(
                    start=start_date,
                    end=end_date,
                    interval='1d',
                )
                
                if df is not None and len(df) > 0:
                    print(f"   ⚠️ Only daily data available for {symbol}")
            
            if df is None or len(df) == 0:
                return None
            
            # Normalize column names
            df = df.reset_index()
            df.columns = [c.lower() for c in df.columns]
            
            # Rename 'date' or 'datetime' to 'timestamp'
            if 'date' in df.columns:
                df = df.rename(columns={'date': 'timestamp'})
            if 'datetime' in df.columns:
                df = df.rename(columns={'datetime': 'timestamp'})
            
            # Ensure timestamp is datetime
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            
            # Remove timezone info if present
            if df['timestamp'].dt.tz is not None:
                df['timestamp'] = df['timestamp'].dt.tz_localize(None)
            
            # Keep only OHLCV columns
            cols = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
            df = df[[c for c in cols if c in df.columns]]
            
            # Fill missing volume with 0
            if 'volume' not in df.columns:
                df['volume'] = 0
            
            print(f"   ✅ Downloaded {len(df):,} candles for {symbol}")
            
            return df
            
        except Exception as e:
            print(f"   ❌ Yahoo error for {symbol}: {e}")
            return None


# ═══════════════════════════════════════════════════════════════════════════
# MAIN DOWNLOAD ORCHESTRATOR
# ═══════════════════════════════════════════════════════════════════════════

def download_all_h1_data(
    assets: List[str] = None,
    start_date: str = START_DATE,
    end_date: str = END_DATE,
    output_dir: Path = DATA_DIR,
    force_redownload: bool = False,
):
    """
    Download H1 data for all assets.
    
    Uses OANDA first, Yahoo Finance as fallback.
    """
    assets = assets or ASSETS
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Initialize downloaders
    oanda = None
    yahoo = None
    
    try:
        oanda = OandaDownloader()
    except Exception as e:
        print(f"⚠️ OANDA not available: {e}")
    
    try:
        yahoo = YahooDownloader()
    except Exception as e:
        print(f"⚠️ Yahoo Finance not available: {e}")
    
    if not oanda and not yahoo:
        raise RuntimeError("No data source available!")
    
    # Track results
    results = {
        'success_oanda': [],
        'success_yahoo': [],
        'failed': [],
        'skipped': [],
    }
    
    print(f"\n{'='*70}")
    print(f"DOWNLOADING H1 DATA FOR {len(assets)} ASSETS")
    print(f"Date range: {start_date} to {end_date}")
    print(f"{'='*70}\n")
    
    for asset in tqdm(assets, desc="Downloading"):
        # Convert to MT5 format (remove underscores) for consistency with D1/H4 files
        mt5_symbol = asset.replace('_', '')
        output_file = output_dir / f"{mt5_symbol}_H1_2014_2025.csv"
        
        # Skip if already exists (unless force redownload)
        if output_file.exists() and not force_redownload:
            print(f"⏭️  {asset} - already exists, skipping")
            results['skipped'].append(asset)
            continue
        
        df = None
        source = None
        
        # Try OANDA first (for forex, metals)
        if oanda:
            try:
                df = oanda.download_full_history(
                    instrument=asset,
                    granularity='H1',
                    start_date=start_date,
                    end_date=end_date,
                )
                if df is not None and len(df) > 0:
                    source = 'oanda'
            except Exception as e:
                print(f"   ⚠️ OANDA failed for {asset}: {e}")
        
        # Fallback to Yahoo Finance
        if df is None and yahoo and asset in YAHOO_SYMBOL_MAP:
            try:
                df = yahoo.download_candles(
                    symbol=asset,
                    yahoo_symbol=YAHOO_SYMBOL_MAP[asset],
                    start_date=start_date,
                    end_date=end_date,
                    interval='1h',
                )
                if df is not None and len(df) > 0:
                    source = 'yahoo'
            except Exception as e:
                print(f"   ⚠️ Yahoo failed for {asset}: {e}")
        
        # Save result
        if df is not None and len(df) > 0:
            # Rename columns to MT5 format for consistency with D1/H4 files
            df = df.rename(columns={
                'timestamp': 'time',
                'open': 'Open',
                'high': 'High',
                'low': 'Low',
                'close': 'Close',
                'volume': 'Volume'
            })
            
            # Ensure columns are in correct order
            df = df[['time', 'Open', 'High', 'Low', 'Close', 'Volume']]
            df.to_csv(output_file, index=False)
            
            print(f"✅ {asset} - {len(df):,} candles saved ({source})")
            
            if source == 'oanda':
                results['success_oanda'].append(asset)
            else:
                results['success_yahoo'].append(asset)
        else:
            print(f"❌ {asset} - FAILED (no data from any source)")
            results['failed'].append(asset)
        
        # Small delay between assets
        time.sleep(0.5)
    
    # Print summary
    print(f"\n{'='*70}")
    print("DOWNLOAD SUMMARY")
    print(f"{'='*70}")
    print(f"✅ Success (OANDA):  {len(results['success_oanda'])}")
    print(f"✅ Success (Yahoo):  {len(results['success_yahoo'])}")
    print(f"⏭️  Skipped:         {len(results['skipped'])}")
    print(f"❌ Failed:          {len(results['failed'])}")
    
    if results['failed']:
        print(f"\nFailed assets: {results['failed']}")
    
    # Save results
    Path('analysis').mkdir(exist_ok=True)
    with open('analysis/h1_download_results.json', 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\n✅ Results saved to: analysis/h1_download_results.json")
    
    return results


# ═══════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Download H1 OHLCV data')
    parser.add_argument('--force', action='store_true', help='Force redownload existing files')
    parser.add_argument('--asset', type=str, help='Download single asset only')
    parser.add_argument('--start', type=str, default=START_DATE, help='Start date')
    parser.add_argument('--end', type=str, default=END_DATE, help='End date')
    
    args = parser.parse_args()
    
    assets = [args.asset] if args.asset else ASSETS
    
    download_all_h1_data(
        assets=assets,
        start_date=args.start,
        end_date=args.end,
        force_redownload=args.force,
    )
