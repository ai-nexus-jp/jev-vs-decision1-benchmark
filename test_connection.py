#!/usr/bin/env python3
"""
互換性ラッパー (test_connection.py -> tests/test_connections.py)
※ アーキテクチャの統一に伴い、本体処理は tests/test_connections.py に移行しました。
"""

import sys
from tests.test_connections import main

if __name__ == "__main__":
    main()
