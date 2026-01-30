# Changelog

## [January 20, 2026]
### Changed
- Updated all documentation to 20K account (was 60K)
- Added two-level backtest architecture documentation
- Cleaned up obsolete documentation files

## [January 18, 2026]
### Added
- Latest simulation results: $310,183 from $20K (+1,451%)
- 871 trades with 67.5% win rate
- Max TDD: 4.94%, Max DDD: 3.61%

## [January 6, 2026]
### Changed
- Simplified from 5-TP to 3-TP exit system
- TP levels: 0.6R/1.2R/2.0R with 35%/30%/35% closes

### Added
- Entry queue system (0.3R proximity, 120h expiry)
- Lot sizing at FILL moment for compounding
- DDD safety system (2%/3%/3.5% tiers)

## [January 5, 2026]
### Fixed
- DDD protection loop timing
- TDD calculation (STATIC from initial balance)

## [January 4, 2026]
### Added
- H1 realistic simulation (`main_live_bot_backtest.py`)
- Challenge risk manager with AccountSnapshot

---

**Last Updated**: January 20, 2026
