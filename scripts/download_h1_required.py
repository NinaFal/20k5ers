#!/usr/bin/env python3
"""
Download H1 data for REQUIRED assets only (from trades file).

Features:
- Downloads only symbols that appear in best_trades_final.csv
- Validates H1 data against D1 (daily high/low should match)
- Date range: 2014-01-01 to 2025-12-31
- Timezone: UTC
"""

import os
import sys
import time
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, List, Dict

import pandas as pd
from dotenv import load_dotenv
from tqdm import tqdm

# Load environment variables
load_dotenv('.env.fiveers_live')

# ═══════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════

# Get required assets from trades file
def get_required_assets():
    trades_path = Path('ftmo_analysis_output/VALIDATE/best_trades_final.csv')
    if trades_path.exists():
        df = pd.read_csv(trades_path)
        # Convert to OANDA format (with underscore)
        symbols = df['symbol'].str.replace('_', '', regex=False).unique()
        # Map back to OANDA format
        result = []
        for s in symbols:
            if len(s) == 6:
                result.append(s[:3] + '_' + s[3:])
            else:
                # Special symbols
                mapping = {
                    'XAUUSD': 'XAU_USD',
                    'XAGUSD': 'XAG_USD',
                    'BTCUSD': 'BTC_USD',
                    'ETHUSD': 'ETH_USD',
                    'NAS100USD': 'NAS100_USD',
                    'SPX500USD': 'SPX500_USD',
                }
                result.append(mapping.get(s, s))
        return sorted(set(result))
    else:
        # Fallback list
        return [
            'EUR_USD', 'GBP_USD', 'USD_JPY', 'USD_CHF', 'AUD_USD', 'USD_CAD', 'NZD_USD',
            'EUR_GBP', 'EUR_JPY', 'EUR_CHF', 'EUR_AUD', 'EUR_CAD', 'EUR_NZD',
            'GBP_JPY', 'GBP_CHF', 'GBP_AUD', 'GBP_CAD', 'GBP_NZD',
            'AUD_JPY', 'AUD_CHF', 'AUD_CAD', 'AUD_NZD',
            'NZD_JPY', 'NZD_CHF', 'NZD_CAD',
            'CHF_JPY', 'CAD_JPY', 'CAD_CHF',
            'XAU_USD', 'XAG_USD',
            'SPX500_USD', 'NAS100_USD',
            'BTC_USD', 'ETH_USD',
        ]

ASSETS = get_required_assets()
DATA_DIR = Path('data/ohlcv')
START_DATE = '2014-01-01'
END_DATE = '2025-12-31'

print(f"Required assets ({len(ASSETS)}): {ASSETS}")


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
        
        # Create API client - practice account
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
        """Download candles for an instrument."""
        params = {
            'granularity': granularity,
        }
        
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
                if candle.get('complete', True):
                    mid = candle.get('mid', {})
                    data.append({
                        'time': candle['time'],
                        'Open': float(mid.get('o', 0)),
                        'High': float(mid.get('h', 0)),
                        'Low': float(mid.get('l', 0)),
                        'Close': float(mid.get('c', 0)),
                        'Volume': int(candle.get('volume', 0)),
                    })
            
            if not data:
                return None
            
            df = pd.DataFrame(data)
            df['time'] = pd.to_datetime(df['time'])
            
            # Remove timezone to make naive (UTC)
            if df['time'].dt.tz is not None:
                df['time'] = df['time'].dt.tz_localize(None)
            
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
        """Download full history by chunking requests."""
        print(f"   📥 Downloading {instrument} {granularity}...")
        
        all_data = []
        current_start = datetime.fromisoformat(start_date)
        end_dt = datetime.fromisoformat(end_date)
        
        # H1: ~180 days per chunk (5000 candles / 24 hours ≈ 208 days)
        chunk_days = 180
        
        request_count = 0
        max_requests = 100
        
        pbar = tqdm(total=int((end_dt - current_start).days / chunk_days) + 1, 
                   desc=f"   {instrument}", leave=False)
        
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
                last_ts = df['time'].max()
                if hasattr(last_ts, 'tz') and last_ts.tz is not None:
                    last_ts = last_ts.tz_localize(None)
                current_start = last_ts + timedelta(hours=1)
            else:
                current_start = chunk_end
            
            request_count += 1
            pbar.update(1)
            time.sleep(0.1)  # Rate limiting
        
        pbar.close()
        
        if not all_data:
            return None
        
        # Combine all chunks
        result = pd.concat(all_data, ignore_index=True)
        result = result.drop_duplicates(subset=['time'], keep='last')
        result = result.sort_values('time').reset_index(drop=True)
        
        print(f"   ✅ {len(result):,} candles")
        
        return result


# ═══════════════════════════════════════════════════════════════════════════
# VALIDATION: H1 vs D1
# ═══════════════════════════════════════════════════════════════════════════

def validate_h1_vs_d1(symbol_mt5: str, h1_df: pd.DataFrame) -> Dict:
    """
    Validate H1 data against D1 data.
    
    Checks:
    1. Daily High in D1 should appear in H1 highs for that day
    2. Daily Low in D1 should appear in H1 lows for that day
    3. Timestamps should be in UTC
    """
    d1_path = DATA_DIR / f"{symbol_mt5}_D1_2003_2025.csv"
    
    if not d1_path.exists():
        return {'status': 'skip', 'reason': 'No D1 file'}
    
    d1_df = pd.read_csv(d1_path)
    d1_df.columns = [c.lower() if c != 'time' else 'time' for c in d1_df.columns]
    
    # Parse timestamps
    if 'time' in d1_df.columns:
        d1_df['time'] = pd.to_datetime(d1_df['time'])
    elif 'datetime' in d1_df.columns:
        d1_df['time'] = pd.to_datetime(d1_df['datetime'])
    
    # Ensure H1 time is datetime
    h1_df['time'] = pd.to_datetime(h1_df['time'])
    
    # Add date column to H1
    h1_df['date'] = h1_df['time'].dt.date
    
    # Aggregate H1 to daily
    h1_daily = h1_df.groupby('date').agg({
        'High': 'max',
        'Low': 'min',
        'Open': 'first',
        'Close': 'last',
    }).reset_index()
    
    # Compare with D1
    d1_df['date'] = d1_df['time'].dt.date
    
    # Merge
    merged = pd.merge(
        h1_daily, d1_df[['date', 'high', 'low']], 
        on='date', 
        suffixes=('_h1', '_d1'),
        how='inner'
    )
    
    if len(merged) == 0:
        return {'status': 'error', 'reason': 'No overlapping dates'}
    
    # Calculate differences
    merged['high_diff'] = abs(merged['High'] - merged['high'])
    merged['low_diff'] = abs(merged['Low'] - merged['low'])
    
    # Allow small tolerance (0.01% of price)
    avg_price = (merged['High'] + merged['Low']).mean() / 2
    tolerance = avg_price * 0.0001
    
    high_match = (merged['high_diff'] <= tolerance).mean() * 100
    low_match = (merged['low_diff'] <= tolerance).mean() * 100
    
    # Find worst mismatches
    worst_high_idx = merged['high_diff'].idxmax()
    worst_low_idx = merged['low_diff'].idxmax()
    
    return {
        'status': 'ok' if high_match > 95 and low_match > 95 else 'warning',
        'days_compared': len(merged),
        'high_match_pct': round(high_match, 2),
        'low_match_pct': round(low_match, 2),
        'worst_high_diff': round(merged.loc[worst_high_idx, 'high_diff'], 6),
        'worst_low_diff': round(merged.loc[worst_low_idx, 'low_diff'], 6),
        'worst_high_date': str(merged.loc[worst_high_idx, 'date']),
        'worst_low_date': str(merged.loc[worst_low_idx, 'date']),
    }


# ═══════════════════════════════════════════════════════════════════════════
# MAIN DOWNLOAD FUNCTION
# ═══════════════════════════════════════════════════════════════════════════

def download_required_h1_data(
    assets: List[str] = None,
    start_date: str = START_DATE,
    end_date: str = END_DATE,
    force_redownload: bool = False,
    validate: bool = True,
):
    """Download H1 data for required assets only."""
    
    assets = assets or ASSETS
    output_dir = DATA_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Initialize OANDA
    try:
        oanda = OandaDownloader()
    except Exception as e:
        print(f"❌ Failed to initialize OANDA: {e}")
        return
    
    results = {
        'success': [],
        'failed': [],
        'skipped': [],
        'validation': {},
    }
    
    print(f"\n{'='*70}")
    print(f"DOWNLOADING H1 DATA FOR {len(assets)} REQUIRED ASSETS")
    print(f"Date range: {start_date} to {end_date}")
    print(f"{'='*70}\n")
    
    for asset in assets:
        mt5_symbol = asset.replace('_', '')
        output_file = output_dir / f"{mt5_symbol}_H1_2014_2025.csv"
        
        # Skip if exists
        if output_file.exists() and not force_redownload:
            print(f"⏭️  {asset} - exists, skipping")
            results['skipped'].append(asset)
            continue
        
        try:
            df = oanda.download_full_history(
                instrument=asset,
                granularity='H1',
                start_date=start_date,
                end_date=end_date,
            )
            
            if df is not None and len(df) > 0:
                # Save
                df.to_csv(output_file, index=False)
                results['success'].append(asset)
                
                # Validate against D1
                if validate:
                    val_result = validate_h1_vs_d1(mt5_symbol, df)
                    results['validation'][asset] = val_result
                    
                    if val_result['status'] == 'ok':
                        print(f"   ✓ Validated: High {val_result['high_match_pct']:.1f}%, Low {val_result['low_match_pct']:.1f}%")
                    elif val_result['status'] == 'warning':
                        print(f"   ⚠️ Validation warning: High {val_result['high_match_pct']:.1f}%, Low {val_result['low_match_pct']:.1f}%")
            else:
                print(f"❌ {asset} - no data")
                results['failed'].append(asset)
                
        except Exception as e:
            print(f"❌ {asset} - error: {e}")
            results['failed'].append(asset)
        
        time.sleep(0.5)
    
    # Summary
    print(f"\n{'='*70}")
    print("DOWNLOAD SUMMARY")
    print(f"{'='*70}")
    print(f"✅ Success: {len(results['success'])}")
    print(f"⏭️  Skipped: {len(results['skipped'])}")
    print(f"❌ Failed:  {len(results['failed'])}")
    
    if results['failed']:
        print(f"\nFailed: {results['failed']}")
    
    # Validation summary
    if results['validation']:
        print(f"\nVALIDATION RESULTS:")
        for asset, val in results['validation'].items():
            status = '✓' if val['status'] == 'ok' else '⚠️' if val['status'] == 'warning' else '?'
            if 'high_match_pct' in val:
                print(f"  {status} {asset}: High={val['high_match_pct']:.1f}%, Low={val['low_match_pct']:.1f}%")
            else:
                print(f"  {status} {asset}: {val.get('reason', 'unknown')}")
    
    # Save results
    Path('analysis').mkdir(exist_ok=True)
    with open('analysis/h1_download_results.json', 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\n✅ Results saved to: analysis/h1_download_results.json")
    
    return results


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Download H1 data for required assets')
    parser.add_argument('--force', action='store_true', help='Force redownload')
    parser.add_argument('--no-validate', action='store_true', help='Skip validation')
    parser.add_argument('--start', type=str, default=START_DATE)
    parser.add_argument('--end', type=str, default=END_DATE)
    
    args = parser.parse_args()
    
    download_required_h1_data(
        start_date=args.start,
        end_date=args.end,
        force_redownload=args.force,
        validate=not args.no_validate,
    )
