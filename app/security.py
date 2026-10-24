"""Защита страниц: nonce для Content-Security-Policy (заголовок — в config.Config.init_app)"""
import secrets

from flask import g


def csp_nonce():
    """Случайный nonce текущего запроса; создаётся при первом обращении.

    Один и тот же для заголовка CSP и для всех встроенных <script nonce="..."> страницы.
    """
    if 'csp_nonce' not in g:
        g.csp_nonce = secrets.token_urlsafe(16)
    return g.csp_nonce
