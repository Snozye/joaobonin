import shutil, os

src = os.path.expanduser('~/Desktop/joaobonin.com/inputs_posts/htb-flight/2026-06-04.rtfd/')
dst = os.path.expanduser('~/Desktop/joaobonin.com/static/images/htb-flight/')

mapping = {
    'Pasted Graphic 11.png': 'ntlm-theft-generate.png',
    'Pasted Graphic 12.png': 'desktop-ini-upload.png',
    'Pasted Graphic 13.png': 'cbum-hash-captured.png',
    'Pasted Graphic 14.png': 'cbum-john-crack.png',
    'Pasted Graphic 15.png': 'cbum-shares.png',
    'Pasted Graphic 18.png': 'webshell-upload.png',
    'Pasted Graphic 19.png': 'cmd-php-whoami.png',
    'Pasted Graphic 20.png': 'svc-apache-revshell.png',
    'Pasted Graphic 21.png': 'msfvenom-payload.png',
    'Pasted Graphic 22.png': 'payload-download.png',
    'Pasted Graphic 23.png': 'msfconsole-svcapache.png',
    'Pasted Graphic 24.png': 'meterpreter-upload.png',
    'Pasted Graphic 25.png': 'runascs-cbum.png',
    'Pasted Graphic 26.png': 'msfconsole-cbum.png',
    'Pasted Graphic 27.png': 'user-flag.png',
    'Pasted Graphic 28.png': 'portfwd-8000.png',
    'Pasted Graphic 30.png': 'netstat-port8000.png',
    'Pasted Graphic 31.png': 'development-site.png',
    'Pasted Graphic 32.png': 'inetpub-development.png',
    'Pasted Graphic 33.png': 'aspx-upload.png',
    'Pasted Graphic 34.png': 'aspx-webshell.png',
    'Pasted Graphic 35.png': 'iisapppool-shell.png',
    'Pasted Graphic 36.png': 'run-taskkill.png',
    'Pasted Graphic 37.png': 'getsystem.png',
    'Pasted Graphic 38.png': 'root-flag.png',
    'Pasted Graphic 39.png': 'whoami-priv.png',
    'Pasted Graphic 40.png': 'systeminfo.png',
    'Pasted Graphic 41.png': 'sharpefspotato.png',
}

for src_name, dst_name in mapping.items():
    s = src + src_name
    d = dst + dst_name
    if os.path.exists(s):
        shutil.copy2(s, d)
        print(f'OK: {dst_name}')
    else:
        print(f'MISSING: {src_name}')
