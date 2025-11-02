#!/usr/bin/env python3
"""
Test runner for the filings ETL system.
Runs all tests and provides a summary.
"""
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest

def main():
    """Run all tests."""
    print("=" * 70)
    print("US-Listed Filings ETL - Unit Test Suite")
    print("=" * 70)
    print()
    
    # Run tests with verbose output
    args = [
        'tests/',
        '-v',                    # Verbose
        '--tb=short',            # Short traceback
        '--color=yes',           # Colored output
        '-r', 'fEsxX',          # Show extra summary info
        '--maxfail=5',          # Stop after 5 failures
    ]
    
    exit_code = pytest.main(args)
    
    print()
    print("=" * 70)
    if exit_code == 0:
        print("✅ ALL TESTS PASSED")
    else:
        print(f"❌ TESTS FAILED (exit code: {exit_code})")
    print("=" * 70)
    
    return exit_code

if __name__ == '__main__':
    sys.exit(main())
