"""macOS Keychain only. No plaintext fallback or embedded user credentials."""
import getpass
import json
import sys

SERVICE = 'JapanPostEMS.LocalAutomation'
ACCOUNT = 'default-login'


def keychain():
    if sys.platform != 'darwin':
        raise RuntimeError('Saving credentials requires macOS Keychain.')
    try:
        from keyring.backends.macOS import Keyring
        return Keyring()
    except Exception:
        raise RuntimeError('macOS Keychain unavailable. Run run.command to install dependencies.') from None


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
        raise RuntimeError('Cannot read Keychain credentials. Reconfigure with setup_login.command or use --manual-login.') from None


def save_login(username, password, backend=None):
    if not isinstance(username, str) or not username.strip() or not isinstance(password, str) or not password:
        raise RuntimeError('Username and password cannot be empty.')
    try:
        (backend or keychain()).set_password(SERVICE, ACCOUNT, json.dumps({'username': username.strip(), 'password': password}))
    except Exception:
        raise RuntimeError('Could not save to macOS Keychain. No plaintext fallback was used.') from None


def setup_login():
    username = input('Japan Post login email / ID: ').strip()
    password = getpass.getpass('Password (hidden; saved to macOS Keychain): ')
    try:
        save_login(username, password)
    finally:
        password = None
    print('Saved to macOS Keychain. Future runs will attempt login; credentials have not yet been verified.')


def forget_login(backend=None):
    try:
        backend = backend or keychain()
        if backend.get_password(SERVICE, ACCOUNT) is not None:
            backend.delete_password(SERVICE, ACCOUNT)
    except Exception:
        raise RuntimeError('Cannot delete Keychain record. Find JapanPostEMS.LocalAutomation in Keychain Access.') from None
