"""建箱限速常量（P2-4 v7.3 抽出为叶子模块，打破 email_pool ↔ tempmail 循环 import）。

temp-mail 系源（tempmail.py/tempmailio.py）与池管理器（email_pool.py）共用，
从环境变量读取，单一来源。
"""

from __future__ import annotations

import os

# temp-mail 建箱最小间隔（秒）：防 429 限流。实测 temp-mail.org 对高频建箱会 429，
# 设 90s 让建箱更稳（24h 不间断约 960 个邮箱），远低于限流阈值。
EMAIL_CREATE_MIN_INTERVAL = int(os.getenv("IF_EMAIL_CREATE_INTERVAL", "90"))
EMAIL_CREATE_BACKOFF = int(os.getenv("IF_EMAIL_CREATE_BACKOFF", "120"))
