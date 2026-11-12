"""macOS Keychain only. No plaintext fallback or embedded user credentials."""
import getpass
import json
import sys

SERVICE = 'JapanPostEMS.LocalAutomation'
ACCOUNT = 'default-login'


def keychain():
    if sys.platform != 'darwin':
        raise RuntimeError('保存登录资料仅支持 Mac 钥匙串。')
    try:
        from keyring.backends.macOS import Keyring
        return Keyring()
    except Exception:
        raise RuntimeError('无法使用 Mac 钥匙串，请先运行新版 run.command 安装依赖。') from None


def load_saved(backend=None):
    try:
        value = (backend or keychain()).get_password(SERVICE, ACCOUNT)
        if value is None:
            return None
        data = json.loads(value)
        if (not isinstance(data, dict) or set(data) != {'username', 'password'}
                or not all(isinstance(data[k], str) and data[k] for k in data)):
            raise ValueError()
        return data
    except Exception:
        raise RuntimeError('未能读取钥匙串登录资料。可运行 setup_login.command 重新设置，或用 --manual-login 自行登录。') from None


def save_login(username, password, backend=None):
    if not isinstance(username, str) or not username.strip() or not isinstance(password, str) or not password:
        raise RuntimeError('账号和密码不能为空。')
    try:
        (backend or keychain()).set_password(SERVICE, ACCOUNT, json.dumps({'username': username.strip(), 'password': password}))
    except Exception:
        raise RuntimeError('未能保存到 Mac 钥匙串；没有改为明文保存。') from None


def setup_login():
    username = input('日本邮政登录邮箱 / ID：').strip()
    password = getpass.getpass('密码（不显示，保存至 Mac 钥匙串）：')
    try:
        save_login(username, password)
    finally:
        password = None
    print('已保存至 Mac 钥匙串。之后正常启动程序会自动尝试登录；尚未验证账号密码是否正确。')


def forget_login(backend=None):
    try:
        backend = backend or keychain()
        if backend.get_password(SERVICE, ACCOUNT) is not None:
            backend.delete_password(SERVICE, ACCOUNT)
    except Exception:
        raise RuntimeError('未能删除钥匙串记录，请在 Mac 钥匙串访问中查找 JapanPostEMS.LocalAutomation。') from None
