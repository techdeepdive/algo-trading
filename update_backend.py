import os

files = ['app.py', 'scanner_backend.py']
for f in files:
    with open(f, 'r') as file:
        content = file.read()
        
    content = content.replace('access_token = data.get("access_token")', 'dhan_pin = data.get("dhan_pin")\n    dhan_totp = data.get("dhan_totp")\n    access_token = data.get("access_token")')
    content = content.replace('if not client_id or not access_token:', 'if not client_id or (not access_token and (not dhan_pin or not dhan_totp)):')
    content = content.replace('tsl = Tradehull(client_id, access_token, mode="access_token")', 'tsl = Tradehull(client_id, mode="pin_totp", pin=dhan_pin, totp_secret=dhan_totp) if dhan_pin and dhan_totp else Tradehull(client_id, access_token, mode="access_token")')
    content = content.replace('if client_id and access_token:', 'if client_id and (access_token or (dhan_pin and dhan_totp)):')
    
    # Signatures
    content = content.replace('def run_screener(client_id, access_token,', 'def run_screener(client_id, access_token, dhan_pin=None, dhan_totp=None,')
    content = content.replace('def start_scanner(client_id, access_token,', 'def start_scanner(client_id, access_token, dhan_pin=None, dhan_totp=None,')
    content = content.replace('def scanner_loop(client_id, access_token,', 'def scanner_loop(client_id, access_token, dhan_pin=None, dhan_totp=None,')
    
    # Calls
    content = content.replace('args=(client_id, access_token, tg_bot, tg_chat,', 'args=(client_id, access_token, dhan_pin, dhan_totp, tg_bot, tg_chat,')
    content = content.replace('start_scanner(client_id, access_token, tg_bot, tg_chat', 'start_scanner(client_id, access_token, dhan_pin, dhan_totp, tg_bot, tg_chat')
    content = content.replace('run_screener(client_id, access_token, strategy_name,', 'run_screener(client_id, access_token, dhan_pin, dhan_totp, strategy_name,')

    with open(f, 'w') as file:
        file.write(content)
