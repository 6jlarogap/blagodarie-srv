#!/usr/bin/env python3
"""
Test script to verify logging configuration
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import settings
from settings import logging

def test_logging():
    print("=" * 50)
    print("TESTING LOGGING CONFIGURATION")
    print("=" * 50)
    
    print(f"Python version: {sys.version}")
    print(f"Settings.DEBUG: {settings.DEBUG}")
    print(f"Settings.TOKEN: {'SET' if settings.TOKEN else 'NOT SET'}")
    print(f"Logging level: {logging.getLogger().level}")
    print(f"Logging handlers: {len(logging.getLogger().handlers)}")
    
    # Test different log levels
    print("\nTesting log levels:")
    logging.debug("This is a DEBUG message")
    logging.info("This is an INFO message")
    logging.warning("This is a WARNING message")
    logging.error("This is an ERROR message")
    
    print("\nLogging test completed successfully!")
    
    # Test importing main modules
    print("\nTesting imports:")
    try:
        from common import AioHttpSessionManager
        print("✓ AioHttpSessionManager imported successfully")
    except Exception as e:
        print(f"✗ Failed to import AioHttpSessionManager: {e}")
    
    try:
        from aiogram import Bot, Dispatcher
        print("✓ Aiogram imported successfully")
    except Exception as e:
        print(f"✗ Failed to import aiogram: {e}")

if __name__ == "__main__":
    test_logging()