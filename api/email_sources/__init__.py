"""邮箱源适配器子包（P2-4 v7.3 自 email_pool.py 拆分）。

每个邮箱源一个文件（base/linshi/mailtm/guerrilla/custom_imap/do22/tempmail/
tempmailio/mailgw/temptf），email_pool.py 保留池管理器逻辑。

向后兼容：`from api.email_pool import XxxSource` 旧路径经 email_pool.py 底部
re-export 仍可用；也可直接 `from api.email_sources import XxxSource`。
"""

from .base import BaseMailSource, MailSource
from .custom_imap import CustomImapSource
from .do22 import Do22Source
from .guerrilla import GuerrillaMailSource
from .linshi import LinshiEmailSource, LinshiMailSource
from .mailgw import MailGwSource
from .mailtm import MailTmSource
from .tempmail import TempMailSource
from .tempmailio import TempMailIoSource
from .temptf import TempTfSource

__all__ = [
    "BaseMailSource",
    "MailSource",
    "CustomImapSource",
    "Do22Source",
    "GuerrillaMailSource",
    "LinshiEmailSource",
    "LinshiMailSource",
    "MailGwSource",
    "MailTmSource",
    "TempMailSource",
    "TempMailIoSource",
    "TempTfSource",
]
