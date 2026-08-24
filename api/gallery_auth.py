"""画廊鉴权由后端统一校验（P0-2 修复：不再前端硬编码密码）。

实现：docs.html 通过 GET /v1/meta 拉取 `gallery_requires_password` 布尔，
有密码要求时对用户展示输入框，输入值作为 query password 传给后端；后端
`if_gallery_password` 用 hmac.compare_digest 比对。前端不保存任何明文密码。

相关后端：api/routes/health.py `GET /v1/meta` 已返回 gallery_requires_password。
"""