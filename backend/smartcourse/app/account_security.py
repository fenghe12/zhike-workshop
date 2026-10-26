"""Persistent, single-use image challenges and authentication attempt limits."""
import base64
import hmac
import io
import secrets
import sqlite3
import time
from pathlib import Path


class AuthSecurityError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


class AccountSecurity:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS challenges (id TEXT PRIMARY KEY, answer TEXT, expires REAL)')
            db.execute('CREATE TABLE IF NOT EXISTS limits (name TEXT PRIMARY KEY, count INTEGER, expires REAL)')
        self.path.chmod(0o600)

    def connect(self):
        return sqlite3.connect(self.path, timeout=10)

    def hit(self, name, maximum, seconds):
        now = time.time()
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('DELETE FROM limits WHERE expires <= ?', (now,))
            row = db.execute('SELECT count FROM limits WHERE name=?', (name,)).fetchone()
            count = row[0] if row else 0
            if count < maximum:
                db.execute('INSERT INTO limits VALUES (?,1,?) ON CONFLICT(name) DO UPDATE SET count=count+1',
                           (name, now + seconds))
        if count >= maximum:
            raise AuthSecurityError('操作过于频繁，请稍后重试。', 429)

    def check_attempts(self, identity):
        with self.connect() as db:
            row = db.execute('SELECT count, expires FROM limits WHERE name=?', ('auth:'+identity,)).fetchone()
        if row and row[1] > time.time() and row[0] >= 12:
            raise AuthSecurityError('登录或注册失败次数较多，请 15 分钟后重试。', 429)

    def failed(self, identity):
        self.hit('auth:'+identity, 12, 15*60)

    def succeeded(self, identity):
        with self.connect() as db:
            db.execute('DELETE FROM limits WHERE name=?', ('auth:'+identity,))

    def issue(self, identity):
        self.hit('captcha:'+identity, 80, 10*60)
        from PIL import Image, ImageDraw, ImageFont
        answer = ''.join(secrets.choice('ABCDEFGHJKLMNPQRSTUVWXYZ23456789') for _ in range(5))
        identifier = secrets.token_urlsafe(24)
        expires = time.time() + 300
        image = Image.new('RGB', (196, 66), '#eef5f0')
        draw = ImageDraw.Draw(image)
        for _ in range(65):
            x, y = secrets.randbelow(196), secrets.randbelow(66)
            draw.ellipse((x,y,x+2,y+2), fill='#9ab7a8')
        font = ImageFont.load_default(size=35)
        for index, character in enumerate(answer):
            draw.text((13+index*34, 10+secrets.randbelow(8)), character, font=font, fill='#174b3c')
        for _ in range(3):
            draw.line((0,secrets.randbelow(66),196,secrets.randbelow(66)),fill='#769e89',width=1)
        data = io.BytesIO(); image.save(data, format='PNG')
        with self.connect() as db:
            db.execute('DELETE FROM challenges WHERE expires <= ?', (time.time(),))
            db.execute('INSERT INTO challenges VALUES (?,?,?)', (identifier, answer, expires))
        return {'id':identifier, 'image':'data:image/png;base64,'+base64.b64encode(data.getvalue()).decode(),
                'expiresInSeconds':300}

    def consume(self, identifier, answer):
        if not isinstance(identifier, str) or not isinstance(answer, str) or not identifier or not answer.strip():
            raise AuthSecurityError('请填写图形验证码。')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT answer, expires FROM challenges WHERE id=?', (identifier,)).fetchone()
            db.execute('DELETE FROM challenges WHERE id=?', (identifier,))
        if not row or row[1] <= time.time():
            raise AuthSecurityError('验证码已过期或已使用，请刷新后重试。')
        supplied = answer.strip().upper()
        if len(supplied) > 16 or not supplied.isascii() or not hmac.compare_digest(row[0], supplied):
            raise AuthSecurityError('验证码不正确，请刷新后重新输入。')
