+++
date = '2026-05-16T00:00:00-03:00'
draft = false
title = 'HTB: Dog - OSCP Prep Write-up'
tags = ['htb', 'oscp', 'lain-kusanagi', 'write-up', 'linux', 'web', 'git', 'gitdumper', 'backdrop-cms', 'credential-reuse', 'wfuzz', 'user-enumeration', 'searchsploit', 'module-upload', 'rce', 'bee', 'gtfobins']
description = 'Write-up for HackTheBox Dog - an exposed .git directory leaks Backdrop CMS source and database credentials, wfuzz user enumeration via the URL aliases pattern yields admin access, a searchsploit RCE module gets repackaged and uploaded, and root comes via bee php-eval under sudo.'
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
- The git log commit message references the Backdrop URL aliases docs, which reveals the `/accounts/[user:name]` pattern - wfuzz enumerates valid usernames, and the DB password logs in as `tiffany`
- Backdrop 1.27.1 has a known authenticated RCE (EDB 52021); the module installer only accepts `tar/tgz/gz/bz2`, so the exploit's zip output needs repackaging before upload - shell as `www-data`
- Two users on the box; the same DB credential switches to `johncusack`
- `sudo -l` shows `bee` (Backdrop's CLI) without a password; `bee php-eval` with `--root` gives root

---

## Recon

### Nmap

![Nmap results](/images/htb-dog/nmap.png)

Ports 22 (SSH) and 80 (HTTP, Apache 2.4.41 Ubuntu). Two things worth flagging immediately: the `http-title` is "Home | Dog", and the `http-git` NSE script flags a Git repository at `/.git/`. The robots.txt entries are all Backdrop CMS paths. Framework and source exposure confirmed in one scan.

---

## Enumeration

### Exposed .git

![.git exposed in browser](/images/htb-dog/git-exposed-browser.png)

The `.GIT` browser extension catches it on the first page load. A publicly accessible `.git` directory means the entire source history is downloadable - including any config files, credentials, or secrets that were ever committed.

### Dumping the repository

![gitdumper running](/images/htb-dog/gitdumper.png)

```bash
gitdumper.py http://10.129.231.223/.git ./git
```

`gitdumper.py` reconstructs the repository from the exposed object store. Once done, `git checkout -- .` restores the working tree.

### Credentials in settings.php

![Dumped git repository contents](/images/htb-dog/git-ls.png)

Full Backdrop CMS source tree, `settings.php` sitting right at the root. Backdrop stores its database connection string in plaintext there.

![settings.php database credentials](/images/htb-dog/settings-php.png)

Database user `root`, password `BackDropJ2024DS2024`. Credential worth keeping - it will show up again.

### User enumeration

![git log commit message](/images/htb-dog/git-log.png)

The only commit in the log says `todo: customize url aliases. reference:https://docs.backdropcms.org/documentation/url-aliases`. That URL is not just a developer note - it fingerprints how the CMS structures user-facing paths.

![Backdrop URL pattern list showing accounts/user:name](/images/htb-dog/url-pattern-doc.png)

The URL aliases documentation reveals the user account pattern: `accounts/[user:name]`. In Backdrop, user profile pages live at `/?q=accounts/<username>`. Non-existent users return 404; valid users return 403 - the page exists but is restricted to the account owner. That difference is all wfuzz needs.

![accounts/test returns Page not found](/images/htb-dog/accounts-not-found.png)

![wfuzz user enumeration results](/images/htb-dog/wfuzz-users.png)

```bash
wfuzz -c -z file,/usr/share/seclists/Usernames/xato-net-10-million-usernames.txt --hc 404 http://10.129.231.223/?q=accounts/FUZZ
```

Filtering out 404s, four valid usernames surface: `john`, `tiffany`, `John`, and `morris`.

![accounts/john returns Access denied](/images/htb-dog/accounts-access-denied.png)

The 403 on a real account confirms the user exists. Trying the DB password `BackDropJ2024DS2024` against each found username, it works for `tiffany`. Added `dog.htb` to `/etc/hosts` and logged in at `/user/login`.

### Version check

![Backdrop CMS status report showing version 1.27.1](/images/htb-dog/status-report.png)

First thing after logging in: **Reports > Status report**. Backdrop CMS 1.27.1. Time to check searchsploit.

---

## Foothold

### Authenticated RCE - EDB 52021

![searchsploit results for Backdrop CMS 1.27.1](/images/htb-dog/searchsploit.png)

Backdrop CMS 1.27.1 has a public authenticated RCE exploit on Exploit-DB.

![Running the exploit to generate the shell module](/images/htb-dog/exploit-run.png)

```bash
searchsploit -m 52021
python3 52021.py http://dog.htb
```

The exploit generates a `shell.zip` module archive with a PHP web shell inside. Before uploading, the default web shell payload was swapped for a Pentestmonkey reverse shell to land an interactive session directly.

One problem: the module installer does not accept zip files.

![Module installer showing accepted file types: tar tgz gz bz2](/images/htb-dog/module-install.png)

The form only takes `tar`, `tgz`, `gz`, or `bz2`. Repackage the shell directory:

![Repackaging shell as tar.gz](/images/htb-dog/tar-archive.png)

Upload `shell.tar.gz` via **Functionality > Install New Modules**, set up a listener, and navigate to `http://dog.htb/modules/shell/shell.php`.

![Shell as www-data](/images/htb-dog/shell-wwwdata.png)

Shell as `www-data`.

### Lateral move to johncusack

![/etc/passwd showing two users with shell access](/images/htb-dog/passwd-users.png)

Two users with shell access beyond root: `jobert` and `johncusack`. The DB password has reused everywhere so far - worth one more try.

![su johncusack with BackDropJ2024DS2024](/images/htb-dog/su-johncusack.png)

`BackDropJ2024DS2024` works for `johncusack`. User flag captured.

---

## Privilege Escalation

### bee via sudo

![sudo -l showing bee NOPASSWD for johncusack](/images/htb-dog/sudo-l.png)

`johncusack` can run `/usr/local/bin/bee` as any user without a password. `bee` is Backdrop's CLI tool - the equivalent of `drush` for Drupal or `wp-cli` for WordPress. It ships with a PHP eval command:

![bee eval command description](/images/htb-dog/bee-eval-desc.png)

Clean path to root - except it does not work out of the box:

![bee eval bootstrap error](/images/htb-dog/bee-eval-error.png)

`The required bootstrap level for 'eval' is not ready.` The tool needs to bootstrap against an actual Backdrop installation. Pointing it at the web root with `--root` fixes it:

![Root shell via sudo bee --root](/images/htb-dog/root-shell.png)

```bash
sudo /usr/local/bin/bee --root=/var/www/html eval "system('/bin/bash');"
```

**Root.**

---

## Takeaways

- **An exposed `.git` on a web server is critical severity.** The entire source history, including credentials and internal configs, is reconstructable by anyone with a gitdumper script. This is a one-command compromise.
- **Commit messages leak methodology.** A todo comment referencing CMS documentation handed over the user enumeration technique. Read every commit message in a dumped repo.
- **Database credentials get reused everywhere.** The same password unlocked the DB connection string, the admin panel, a system user account, and the sudo password prompt. Every credential you find is worth trying against every login surface.
- **CMS version fingerprinting is high-value.** Checking Reports > Status report immediately revealed a version with a public RCE. Version-check any CMS you get authenticated access to.
- **`sudo` on a CLI tool with eval/exec capabilities is an instant root.** `bee`, `drush`, `wp-cli`, and similar tools all have PHP eval or shell-command features. If any of them appear in `sudo -l`, it is game over.

## References

- [HackTheBox - Dog](https://app.hackthebox.com/machines/Dog)
- [GitDumper - git-dumper](https://github.com/arthaud/git-dumper)
- [EDB 52021 - Backdrop CMS 1.27.1 Authenticated RCE](https://www.exploit-db.com/exploits/52021)
- [GTFOBins - bee](https://gtfobins.github.io/gtfobins/bee/)
- Lain Kusanagi list (OSCP prep)
