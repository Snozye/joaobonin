+++
date = '2026-05-19T00:00:00-03:00'
draft = false
title = 'HTB: Access - OSCP Prep Write-up'
tags = ['htb', 'oscp', 'lain-kusanagi', 'write-up', 'windows', 'easy', 'ftp', 'telnet', 'mdb', 'credentials', 'pst', 'runas']
description = 'Write-up for the HackTheBox machine Access - chaining anonymous FTP, a Microsoft Access database, an AES-encrypted ZIP, and a PST email file to uncover credentials for Telnet login and privilege escalation via saved Windows credentials.'
ShowToc = true
TocOpen = false
[cover]
image = 'images/htb-access/cover.png'
+++

Old school. Access is a machine that takes you through a chain of credential pivoting across legacy protocols and file formats you do not see every day - no exploits, no CVEs, just enumeration and following the breadcrumbs wherever they lead.

## Machine info

| | |
|---|---|
| **Name** | Access |
| **Platform** | HackTheBox |
| **OS** | Windows |
| **Difficulty** | Easy |

## TL;DR

- Anonymous FTP exposes `backup.mdb` (Microsoft Access database) and `Access Control.zip` (AES-encrypted)
- `backup.mdb` contains an `auth_user` table with credentials - including the password to decrypt the ZIP
- The ZIP holds a PST file; reading the extracted email reveals the `security` account password in plaintext
- Telnet login as `security` -> user shell
- `cmdkey /list` shows saved credentials for `ACCESS\Administrator`; `runas /savecred` gives Administrator access

---

## Enumeration

Port 21 was open and I went straight for it - anonymous FTP is one of those findings you want to verify immediately.

![FTP connection to 10.129.35.25 with anonymous login - 230 User logged in, Windows_NT system](/images/htb-access/ftp-anonymous.png)

In. Now let's run a proper nmap to map the full attack surface while we explore.

![Nmap output showing port 21 FTP (anonymous allowed), 23 Telnet (Windows XP telnetd, TARGET: ACCESS), 80 HTTP (IIS 7.5, title: MegaCorp)](/images/htb-access/nmap-results.png)

Three services: FTP on 21, Telnet on 23, and IIS 7.5 on 80. The hostname is ACCESS and the web title reads MegaCorp. HTTP turned out to be a static dead end - nothing interesting there. The real action is in FTP.

### FTP - browsing the shares

Back in FTP, let's see what is actually in here:

![FTP ls -la showing Backups directory (08-23-18) and Engineer directory (08-24-18)](/images/htb-access/ftp-directories.png)

Two directories: `Backups` and `Engineer`. `Backups` has `backup.mdb`, `Engineer` has `Access Control.zip`. Both are worth grabbing. FTP needs to be switched to binary mode first - without it, binary files come back corrupted.

![FTP bin command (Type set to I), ls Backups shows backup.mdb 5652480 bytes, get backup.mdb - 100% transfer complete](/images/htb-access/ftp-binary-download.png)

Binary mode set, `backup.mdb` downloaded. Same process for `Access Control.zip` from the Engineer directory (not shown separately).

### Cracking the ZIP

First thing I tried when I got the zip:

![unzip Access Control.zip - skipping Access Control.pst: unsupported compression method 99](/images/htb-access/unzip-aes-error.png)

Error 99 means AES-256 encryption. Standard `unzip` cannot handle it - we need 7-Zip. Before reaching for the password we found, let's see if it cracks with John first:

![zip2john "Access Control.zip" > hash](/images/htb-access/zip2john.png)

```bash
john hash --wordlist=/usr/share/wordlists/rockyou.txt
```

No result against rockyou. That dead end closes fast. Time to dig into the other file.

### Digging into backup.mdb

![file backup.mdb - Microsoft Access Database; sudo apt install mdbtools command](/images/htb-access/file-backup-mdb.png)

`file` confirms it is a Microsoft Access database. The `mdbtools` package can dump tables from it on Linux:

![mdb-export backup.mdb showing a large list of table names including auth_user](/images/htb-access/mdb-tables.png)

Lots of tables. The one that jumps out immediately is `auth_user`.

![mdb-export backup.mdb auth_user: id, username, password columns - admin/admin, engineer/access4u@security, backup_admin/admin](/images/htb-access/mdb-auth-user.png)

Credentials in plaintext:

| username | password |
|---|---|
| admin | admin |
| engineer | `access4u@security` |
| backup_admin | admin |

The `engineer` password stands out. `access4u@security` looks deliberate - and we have a locked ZIP file sitting right next to this database.

### Unlocking the ZIP

```bash
7za x -p"access4u@security" "Access Control.zip"
```

![7za extracting Access Control.zip with password access4u@security - Everything is Ok, extracted Access Control.pst](/images/htb-access/7za-extract.png)

The password worked. The archive contained `Access Control.pst` - an Outlook Personal Storage file.

### Reading the PST

PST files are Outlook mailboxes. `readpst` converts them to `.mbox` format readable as plain text:

![file Access Control.pst - Microsoft Outlook Personal Storage; readpst converting it, processing Deleted Items folder, 2 items done](/images/htb-access/readpst.png)

![cat Access Control.mbox - email from john@megacorp.com to security@accesscontrolsystems.com - body reads: "The password for the security account has been changed to 4Cc3ssC0ntr0ller. Please ensure this is passed on to your engineers."](/images/htb-access/mbox-password.png)

An internal MegaCorp email sent to the `security` account at Access Control Systems. The body reads:

> The password for the "security" account has been changed to **4Cc3ssC0ntr0ller**. Please ensure this is passed on to your engineers.

New credential: `security` / `4Cc3ssC0ntr0ller`. And we have Telnet open on port 23.

---

## Foothold

![telnet 10.129.35.25 23 - connected, Microsoft Telnet Service banner, login: security, C:\Users\security> whoami: access\security](/images/htb-access/telnet-login.png)

Shell as `security`.

![C:\Users\security\Desktop> type user.txt - 8aa2feccd8413c6bed6817fdf0e351c8](/images/htb-access/user-flag.png)

User flag.

---

## Privilege Escalation

### Saved credentials - Windows Credential Manager

Windows has a feature called Credential Manager that lets programs store credentials for reuse. When credentials are saved there, you can invoke them via `runas /savecred` without knowing the actual password - the OS fills it in from cache. Worth checking early on any Windows box:

```cmd
cmdkey /list
```

```
Currently stored credentials:
    Target: Domain:interactive=ACCESS\Administrator
    Type: Domain Password
    User: ACCESS\Administrator
```

Administrator credentials are cached. We can use this to run arbitrary commands as Administrator - no password needed:

```cmd
runas /savecred /user:ACCESS\Administrator "cmd.exe /c type C:\Users\Administrator\Desktop\root.txt > C:\Users\security\Desktop\root.txt"
```

```cmd
type C:\Users\security\Desktop\root.txt
```

Root flag.

---

## Takeaways

- **Legacy services are goldmines.** FTP and Telnet are ancient, but they still show up in environments with older infrastructure. Anonymous FTP login is an immediate red flag worth fully exploring - do not just note it and move on.
- **Credentials chain across formats.** The full path here: MDB database -> ZIP password -> PST email -> account password. Each file format was a stepping stone. When you find credentials, ask where else they might apply - and when you find an encrypted file, go looking for its key elsewhere in the same environment.
- **`cmdkey /list` on every Windows box.** If Administrator credentials are cached, `runas /savecred` gives you full execution as that user without ever needing to crack anything. It is one of those quiet privesc paths that is easy to miss if you skip the credential check.

---

## References

- [HackTheBox - Access](https://www.hackthebox.com/machines/access)
- [mdbtools - GitHub](https://github.com/mdbtools/mdbtools)
- [Windows Privilege Escalation via runas /savecred](https://www.hackingarticles.in/windows-privilege-escalation-runas/)
