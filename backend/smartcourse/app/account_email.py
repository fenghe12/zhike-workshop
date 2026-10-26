"""Email challenges with explicit SMTP configuration and private persistent state."""
import os
import re
import secrets
import smtplib
import ssl
import time
from email.message import EmailMessage
from pathlib import Path

from .account_security import AuthSecurityError


def email_address(value):
    value = str(value or '').strip().lower()
    if len(value) > 254 or not re.fullmatch(r'[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+', value):
        raise ValueError('请填写有效的邮箱地址。')
    return value


class AccountEmail:
    def __init__(self, security, sender=None):
        self.security = security
        self.sender = sender
        with security.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS email_challenges '
                       '(email TEXT, purpose TEXT, code TEXT, expires REAL, attempts INTEGER, '
                       'PRIMARY KEY(email,purpose))')

    @property
    def enabled(self):
        return self.sender is not None or bool(os.environ.get('SMARTCOURSE_SMTP_HOST')
                                               and os.environ.get('SMARTCOURSE_SMTP_FROM'))

    def send(self, address, purpose, identity):
        if not self.enabled:
            raise AuthSecurityError('邮箱服务暂未启用，请联系项目管理员。', 503)
        address = email_address(address)
        if purpose not in {'register', 'bind', 'reset'}:
            raise ValueError('邮箱验证用途无效。')
        self.security.hit('email-ip:'+identity, 12, 3600)
        self.security.hit('email-address:'+address, 1, 60)
        code = ''.join(secrets.choice('0123456789') for _ in range(6))
        with self.security.connect() as db:
            db.execute('DELETE FROM email_challenges WHERE expires <= ?', (time.time(),))
            db.execute('INSERT OR REPLACE INTO email_challenges VALUES (?,?,?,?,0)',
                       (address, purpose, code, time.time()+600))
        try:
            (self.sender or self._smtp_send)(address, code)
        except Exception as exc:
            with self.security.connect() as db:
                db.execute('DELETE FROM email_challenges WHERE email=? AND purpose=?', (address, purpose))
            raise AuthSecurityError('邮件发送失败，请稍后重试。', 503) from exc
        return {'sent': True, 'expiresInSeconds': 600, 'retryAfterSeconds': 60}

    @staticmethod
    def _smtp_send(address, code):
        host = os.environ['SMARTCOURSE_SMTP_HOST']
        port = int(os.environ.get('SMARTCOURSE_SMTP_PORT', '465'))
        username = os.environ.get('SMARTCOURSE_SMTP_USER', '')
        password_file = os.environ.get('SMARTCOURSE_SMTP_PASSWORD_FILE')
        password = Path(password_file).read_text().strip() if password_file else os.environ.get('SMARTCOURSE_SMTP_PASSWORD', '')
        message = EmailMessage()
        message['From'] = os.environ['SMARTCOURSE_SMTP_FROM']
        message['To'] = address
        message['Subject'] = '智课工坊 / Smartcourse verification code'
        message.set_content('智课工坊验证码 / Your Smartcourse verification code: '+code+
                            '\n10 分钟内有效 / Valid for 10 minutes.\n请勿向他人提供验证码。')
        context = ssl.create_default_context()
        secure = os.environ.get('SMARTCOURSE_SMTP_SECURITY', 'ssl')
        if secure not in {'ssl', 'starttls'}:
            raise ValueError('SMTP requires encrypted transport')
        smtp = smtplib.SMTP_SSL(host, port, timeout=20, context=context) if secure == 'ssl' else smtplib.SMTP(host, port, timeout=20)
        with smtp:
            if secure == 'starttls':
                smtp.starttls(context=context)
            if username:
                smtp.login(username, password)
            smtp.send_message(message)

    def consume(self, address, purpose, code):
        address = email_address(address)
        supplied = str(code or '')
        valid = False
        with self.security.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT code,expires,attempts FROM email_challenges WHERE email=? AND purpose=?',
                             (address, purpose)).fetchone()
            if row and row[1] > time.time() and row[2] < 5:
                valid = supplied.isascii() and secrets.compare_digest(row[0], supplied)
                if valid:
                    db.execute('DELETE FROM email_challenges WHERE email=? AND purpose=?', (address, purpose))
                else:
                    db.execute('UPDATE email_challenges SET attempts=attempts+1 WHERE email=? AND purpose=?',
                               (address, purpose))
        if not valid:
            raise AuthSecurityError('邮箱验证码不正确、已过期或已使用。')
        return address
