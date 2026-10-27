#!/usr/bin/env python3
"""
互換性ラッパー (evaluate_models.py -> evaluate.py)
※ アーキテクチャの統一に伴い、本体処理は evaluate.py に移行しました。
※ 本スクリプトは後方互換性のために残されており、evaluate.py を透過的に実行します。
"""

import sys
from evaluate import main

if __name__ == "__main__":
    main()
