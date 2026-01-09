"""
Utils module for tradr package.

Note: state.py is deprecated and moved to _deprecated/
"""

from .logger import setup_logger
from .output_manager import OutputManager

__all__ = ['setup_logger', 'OutputManager']
