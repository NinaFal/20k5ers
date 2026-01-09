"""
MT5 module for tradr package.

Provides MT5 trading functionality via client.py
Note: bridge_client.py is deprecated and moved to _deprecated/
"""

from .client import MT5Client

__all__ = ['MT5Client']
