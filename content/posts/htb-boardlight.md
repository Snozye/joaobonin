+++
date = '2026-04-21T00:00:00-03:00'
draft = false
title = 'HTB: BoardLight - OSCP Prep Write-up'
tags = ['htb', 'oscp', 'lain-kusanagi', 'write-up', 'linux', 'web', 'dolibarr', 'cve', 'suid']
description = 'Write-up for the HackTheBox machine BoardLight - subdomain enumeration, Dolibarr RCE via CVE-2023-30253, credential reuse for SSH, and Enlightenment SUID privesc via CVE-2022-37706.'
ShowToc = true
TocOpen = false
[cover]
image = 'images/htb-boardlight/cover.png'
+++

BoardLight chains together a few classic techniques: subdomain discovery leading to an exposed ERP, authenticated RCE via a known CVE, credential reuse to pivot to a real user, and a SUID binary chain to root.

## Machine info

| | |
|---|---|
| **Name** | BoardLight |
| **Platform** | HackTheBox |
| **OS** | Linux |
| **Difficulty** | Easy |

## TL;DR

- Subdomain enumeration reveals `crm.board.htb` running **Dolibarr 17.0.0**
- Default `admin:admin` credentials get us in
- **CVE-2023-30253** - PHP code injection via the website module - gives shell as `www-data`
- Database credentials in `conf.php` are reused by user `larissa` for SSH
- **CVE-2022-37706** - Enlightenment SUID LPE - escalates to root

---

## Recon

### Nmap

```bash
nmap -sV -sC -Pn -A 10.129.0.0
```

![Nmap results](/images/htb-boardlight/nmap.png)

Open ports: **22** (SSH) and **80** (HTTP).

---

## Enumeration

### Subdomain discovery

![Dolibarr login](/images/htb-boardlight/dolibarr-login.png)

Found: `crm.board.htb`. Added to `/etc/hosts`.

### Dolibarr login page

Navigating to `crm.board.htb` shows a **Dolibarr** login page. Dolibarr is an open-source ERP and CRM platform widely used by small and medium businesses. The version is exposed on the login page:
![Exploit shell](/images/htb-boardlight/exploit-shell.png)

Default credentials `admin:admin` work - we're in.

---

## Foothold
 
### CVE-2023-30253 - PHP code injection in Dolibarr

A quick research shows Dolibarr is vulnerable to CVE-2023-30253. This CVE is a PHP code injection vulnerability. The website module's page editor allows authenticated users to create dynamic content with PHP. While the application tries to block `<?php` tags, the filter can be bypassed using mixed-case (`<?PHP`), allowing arbitrary PHP execution in the context of the web server.

References:
- [TinextaCyber advisory](https://www.tinextacyber.com/security-advisory-dolibarr-17-0-0-php-code-injection-cve-2023-30253/)
- [PoC exploit](https://github.com/nikn0laty/Exploit-for-Dolibarr-17.0.0-CVE-2023-30253/tree/main)


![SSH as larissa](/images/htb-boardlight/ssh-larissa.png)


Shell as `www-data`.

---

## Privilege Escalation

### Step 1 - Credential reuse via conf.php

Browsing to the Dolibarr config file at `/var/www/html/crm.board.htb/htdocs/conf/conf.php` I found database credentials:

![LinPEAS SUID binaries](/images/htb-boardlight/linpeas-suid.png)


These don't work for the database directly, but the password is reused by **larissa** - a user found in `/etc/passwd`.

### SSH as larissa

```bash
ssh larissa@board.htb
```


### Step 2 - Enlightenment SUID LPE (CVE-2022-37706)

Running LinPEAS reveals several unusual SUID binaries:


```
/usr/lib/x86_64-linux-gnu/enlightenment/utils/enlightenment_sys
/usr/lib/x86_64-linux-gnu/enlightenment/utils/enlightenment_ckpasswd
/usr/lib/x86_64-linux-gnu/enlightenment/utils/enlightenment_backlight
/usr/lib/x86_64-linux-gnu/enlightenment/modules/cpufreq/linux-gnu-x86_64-0.23.1/freqset
```

Enlightenment is a lightweight window manager and desktop environment for Linux. 
By checking Enlightenment's version it shows `0.23.1`:

![CVE-2022-37706 exploit running](/images/htb-boardlight/cve-exploit.png)


I found this version is vulnerable to **CVE-2022-37706**. It's a local privilege escalation vulnerability in its SUID utility binaries, they fail to properly sanitize user-controlled input before passing it to privileged operations, allowing an unprivileged user to execute arbitrary commands as root.

I copied this POC to the machine: [CVE-2022-37706 exploit](https://github.com/MaherAzzouzi/CVE-2022-37706-LPE-exploit/blob/main/PublicReferenceURL.txt)


![Root shell](/images/htb-boardlight/root-shell.png)

**Root!**

---

## Takeaways (for OSCP)

- **Always enumerate subdomains, not just directories.** The main `board.htb` site had nothing - the attack surface was entirely on the subdomain. Virtual host fuzzing is a must.
- **Version disclosure on login pages is a gift.** Dolibarr showed its version without authentication. That single piece of information mapped directly to a working RCE CVE.
- **Check config files after getting a foothold.** Database config files like `conf.php` or `wp-config.php` frequently contain credentials reused by system users for SSH.
- **Run LinPEAS and pay attention to unknown SUID binaries.** Standard SUID binaries are expected, but unusual ones tied to specific software versions are worth investigating immediately.

## References

- [HackTheBox - BoardLight](https://app.hackthebox.com/machines/BoardLight)
- [CVE-2023-30253 - Dolibarr PHP Code Injection advisory](https://www.tinextacyber.com/security-advisory-dolibarr-17-0-0-php-code-injection-cve-2023-30253/)
- [CVE-2023-30253 PoC](https://github.com/nikn0laty/Exploit-for-Dolibarr-17.0.0-CVE-2023-30253/tree/main)
- [CVE-2022-37706 PoC](https://github.com/MaherAzzouzi/CVE-2022-37706-LPE-exploit/blob/main/PublicReferenceURL.txt)
- Lain Kusanagi list (OSCP prep)
