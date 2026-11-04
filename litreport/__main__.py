# -*- coding: utf-8 -*-
"""允许 `python -m litreport ...` 直接跑。"""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
