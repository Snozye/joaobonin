+++
date = '2026-04-17T00:00:00-03:00'
draft = false
title = 'HTB: Nibbles - OSCP Prep Write-up'
tags = ['htb', 'oscp', 'lain-kusanagi', 'write-up', 'linux', 'web', 'rce', 'nibbleblog', 'suid']
description = 'Write-up for the HackTheBox machine Nibbles - part of my OSCP preparation journey following the Lain Kusanagi list.'
ShowToc = true
TocOpen = false

[cover]
image = 'images/htb-nibbles/cover.png'
+++

Another one down from the **Lain Kusanagi list** - this time it's **Nibbles**, an Easy Linux box. Classic web enumeration into authenticated RCE, with a clean sudo privesc to wrap it up.

## Machine info

| | |
|---|---|
| **Name** | Nibbles |
| **Platform** | HackTheBox |
| **OS** | Linux |
| **Difficulty** | Easy |

## TL;DR

- Nibbleblog v4.0.3 with default credentials (`admin:nibbles`)
- Authenticated file upload RCE (CVE-2015-6967) for initial shell as `nibbler`
- `sudo -l` reveals `monitor.sh` can be run as root with NOPASSWD
- Overwrite `monitor.sh` with SUID payload on `/bin/bash` to get root

---

## Recon

### RustScan + Nmap

```bash
rustscan -a 10.129.20.162 -- -sV -sC -Pn -A
```

![Nmap results](/images/htb-nibbles/nmap-results.png)

- **Port 22**: OpenSSH 7.2p2 Ubuntu
- **Port 80**: Apache 2.4.18 (Ubuntu)

### Web service

Browsing to port 80 shows a simple "Hello world!" page. Checking the source code reveals an HTML comment pointing to `/nibbleblog/`:

![Hello world with source](/images/htb-nibbles/hello-world.png)

Navigating to `/nibbleblog/` shows a blog powered by **Nibbleblog**:

![Nibbleblog homepage](/images/htb-nibbles/nibbleblog.png)

---

## Enumeration

### Directory brute force

```bash
feroxbuster --url http://10.129.20.162/nibbleblog/ -w /usr/share/wordlists/dirb/common.txt
```

Feroxbuster returned many results. Notable findings:

![Feroxbuster results](/images/htb-nibbles/feroxbuster-results.png)

- `/nibbleblog/admin.php` - login form
- `/nibbleblog/content/` - directory listing with interesting files
- `/nibbleblog/README` - version disclosure

### Admin login

![Admin login form](/images/htb-nibbles/admin-login.png)

### Exposed config and version

`/nibbleblog/content/private/config.xml` exposed the username **admin**:

![config.xml with admin user](/images/htb-nibbles/config-xml.png)

`/nibbleblog/README` disclosed the exact version - **Nibbleblog v4.0.3**:

![README with version](/images/htb-nibbles/readme-version.png)

### CVE-2015-6967

A quick search showed **CVE-2015-6967** - Nibbleblog 4.0.3 File Upload Authenticated RCE. However, this CVE requires valid credentials.

I was about to move on when I remembered that in a past CTF, the password was simply the machine's name. Tried `admin:nibbles` and it worked.

---

## Foothold

### Nibbleblog File Upload RCE

With valid credentials, I used the exploit for CVE-2015-6967. First, tested RCE with `whoami`:

![RCE confirmed](/images/htb-nibbles/exploit-rce.png)

RCE confirmed - running as `nibbler`. Now for a reverse shell:

![Exploit reverse shell](/images/htb-nibbles/exploit-revshell.png)

### Shell as nibbler

![Shell as nibbler](/images/htb-nibbles/shell-nibbler.png)

Got a shell as `nibbler`.

---

## Privilege Escalation

### sudo -l

One of the first things I do when landing on a machine is `sudo -l`:

![sudo -l output](/images/htb-nibbles/sudo-l.png)

We can run `monitor.sh` as root without a password.

### personal.zip

Under nibbler's home directory, there's a `personal.zip` file. Extracting it reveals the `monitor.sh` script:

![personal.zip extraction](/images/htb-nibbles/personal-zip.png)

Since we have full control over nibbler's home directory, we can simply overwrite `monitor.sh` with whatever we want.

### SUID on /bin/bash

I chose to set the SUID bit on `/bin/bash`:

```bash
echo "chmod +s /bin/bash" > monitor.sh
sudo ./monitor.sh
```

After running the script as root, the SUID bit was set:

![SUID confirmed](/images/htb-nibbles/suid-confirm.png)

The SUID (Set User ID) bit means that when any user runs `/bin/bash`, it executes with the file owner's privileges - in this case, root. The `-p` flag tells bash to not drop these elevated privileges, giving us a root shell:

![Root shell](/images/htb-nibbles/root-shell.png)

**Root!**

---

## Takeaways (for OSCP)

- **Always try obvious passwords.** Machine name, service name, "admin", "password" - it sounds dumb, but it works more often than you'd think. In the exam, don't skip the low-hanging fruit.
- **Check `sudo -l` immediately after landing.** This is one of the fastest privesc paths and appears frequently in the OSCP.
- **Writable files that run as root = instant win.** If you can modify a script that `sudo` lets you run as root, game over. Always check file permissions.
- **Read the source code and comments.** The HTML comment pointing to `/nibbleblog/` was the entry point. Never skip view-source.

## References

- [HackTheBox - Nibbles](https://app.hackthebox.com/machines/Nibbles)
- [CVE-2015-6967 - Nibbleblog File Upload RCE](https://cve.mitre.org/cgi-bin/cvename.cgi?name=CVE-2015-6967)
- Lain Kusanagi list (OSCP prep)
