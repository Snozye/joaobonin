---
title: "HTB Monteverde - Azure AD Connect Password Extraction"
date: 2026-06-01
draft: false
tags:
  - htb
  - windows
  - medium
  - smb
  - ldap
  - active-directory
  - password-spray
  - azure-ad-connect
  - privesc
  - write-up
description: "Monteverde is a Medium Windows Active Directory box from HackTheBox. We enumerate domain users via null session, discover a username-as-password credential for SABatchJobs, find an Azure AD Connect config file containing plaintext credentials in an SMB share, and escalate to Administrator by decrypting the Azure AD Sync service account password from the local MSSQL Express database."
ShowToc: true
cover:
  image: "/images/htb-monteverde/cover.png"
  alt: "Monteverde HTB machine cover image"
---

Machine #48 on the Lain Kusanagi list. Active Directory, a forgotten config file, and the Azure AD Sync service doing what it really shouldn't.

## Machine Info

| Field      | Details                        |
|------------|--------------------------------|
| Name       | Monteverde                     |
| Platform   | HackTheBox                     |
| OS         | Windows                        |
| Difficulty | Medium                         |
| IP         | 10.129.228.111                 |
| Domain     | MEGABANK.LOCAL                 |

## TL;DR

Null session via nxc gives a full user list. A password spray with username=password lands `SABatchJobs:SABatchJobs`. Listing SMB shares reveals `users$` is readable - spider_plus finds `mhope/azure.xml`, a leftover Azure AD Connect config file with a cleartext password. Spray again, get `mhope` via WinRM. mhope is in the Azure Admins group and the ADSync service is running locally. A public PoC decrypts the ADSync credentials from the local MSSQL database, handing us domain administrator.

## Recon

{{< figure src="/images/htb-monteverde/nmap.png" alt="nmap scan showing ports 53 88 135 139 389 445 464 593 636 3268 3269 5985 9389 open, confirming a Windows Domain Controller with MEGABANK.LOCAL domain" >}}

Classic DC fingerprint: Kerberos on 88, LDAP on 389/636, Global Catalog on 3268/3269, SMB on 445, WinRM on 5985. The LDAP banner confirms the domain is `MEGABANK.LOCAL`. Port 9389 is the AD Web Services endpoint. No web app, so the attack surface is pure AD.

## Enumeration

### Null Session - User List

nxc's SMB null authentication pulled a full list of domain users without any credentials:

{{< figure src="/images/htb-monteverde/enum-users.png" alt="nxc smb null session enumerating 18 domain users including SABatchJobs mhope AAD_987d7f dgalanos roleary smorgan" >}}

18 users. A few stand out: `SABatchJobs` sounds like a service account that might have a weak password, and `AAD_987d7f` has the naming pattern of an auto-generated Azure AD Connect sync account. That second one goes in the mental backlog.

### Password Spray - Username as Password

With a user list, the cheapest check is whether any account has its username as its password. `--no-bruteforce` pairs each user with their own name:

{{< figure src="/images/htb-monteverde/password-spray-sabatchjobs.png" alt="nxc smb password spray showing SABatchJobs:SABatchJobs as valid, AAD_987d7f and mhope failing" >}}

`SABatchJobs:SABatchJobs`. Told you. Service accounts set up with a "temporary" password that never gets rotated are a gift that keeps giving.

### SMB Shares

With valid credentials, let's see what we can reach:

{{< figure src="/images/htb-monteverde/smb-shares.png" alt="nxc smb share enumeration as SABatchJobs showing azure_uploads READ users$ READ IPC$ NETLOGON SYSVOL accessible" >}}

Two readable non-standard shares: `azure_uploads` and `users$`. The name `azure_uploads` combined with the `AAD_987d7f` account from earlier is already telling a story. `users$` is a home directory share - that's worth spelunking.

### Finding azure.xml

Downloading directly from `users$`:

{{< figure src="/images/htb-monteverde/azure-xml-download.png" alt="nxc smb command downloading mhope/azure.xml from the users$ share to local azure.xml" >}}

spider_plus confirmed what was in there:

{{< figure src="/images/htb-monteverde/spider-plus-output.png" alt="spider_plus JSON output showing mhope/azure.xml file 1.18 KB in the users$ share" >}}

A 1.18 KB XML file in mhope's home folder, named `azure.xml`. Let's see what's inside:

{{< figure src="/images/htb-monteverde/azure-xml-content.png" alt="cat azure.xml showing a PSADPasswordCredential object with password 4n0therD4y@n0th3r$ in plaintext" >}}

A serialized `Microsoft.Azure.Commands.ActiveDirectory.PSADPasswordCredential` object. This is exactly what gets created when someone runs Azure AD Connect setup via PowerShell and doesn't clean up after themselves. The `<S N="Password">` field is cleartext: `4n0therD4y@n0th3r$`.

### Password Spray - Round 2

Spray that password against the user list:

{{< figure src="/images/htb-monteverde/mhope-spray.png" alt="nxc smb spray showing mhope:4n0therD4y@n0th3r$ as valid credentials" >}}

`mhope:4n0therD4y@n0th3r$`. The file was sitting in their home directory, so this tracks.

I also ran spider_plus for a broader look at what SABatchJobs could reach across all shares:

{{< figure src="/images/htb-monteverde/spider-plus.png" alt="nxc smb spider_plus module running as SABatchJobs against MONTEVERDE" >}}

## Foothold

WinRM is open on 5985. Let's test mhope directly and grab user.txt in one shot:

{{< figure src="/images/htb-monteverde/user-flag.png" alt="nxc winrm executing type user.txt as mhope showing Pwnd and user flag 780161b0b1dd87325774901e5b182250" >}}

WinRM access confirmed. Shell via evil-winrm:

```bash
evil-winrm -i 10.129.228.111 -u mhope -p '4n0therD4y@n0th3r$'
```

## Privilege Escalation

### Azure Admins Group

First thing in the shell - check what groups mhope belongs to:

{{< figure src="/images/htb-monteverde/whoami-groups.png" alt="whoami /groups output showing mhope is a member of MEGABANK\\Azure Admins group" >}}

`MEGABANK\Azure Admins`. With an Azure AD Connect sync account (`AAD_987d7f`) spotted during recon and the Azure Admins membership here, the path is becoming clear.

### ADSync is Running

{{< figure src="/images/htb-monteverde/adsync-service.png" alt="Get-Service ADSync showing Status Running Name ADSync DisplayName Microsoft Azure AD Sync" >}}

The ADSync service is alive. This means Azure AD Connect is actively syncing credentials between the local AD and Azure AD. To do that, it needs a service account with `DS-Replication-Get-Changes-All` rights - effectively DCSync permissions. Those credentials are stored locally, encrypted with DPAPI.

The attack: Azure AD Connect stores the sync credentials in a local MSSQL Express database (`localhost\ADSync`). The encryption key is tied to the machine account via DPAPI. Anyone who can query that database and access the DPAPI key material can decrypt the credentials - and Azure Admins can do exactly that.

There is a well-known PoC for this from [xpnsec](https://blog.xpnsec.com/azuread-connect-for-redteam/). Upload it to the evil-winrm session, import, and run:

```powershell
upload Get-MSOLDecryptedCredentials.ps1
Import-Module .\Get-MSOLDecryptedCredentials.ps1
Get-MSOLDecryptedCredentials
```

{{< figure src="/images/htb-monteverde/adsync-decrypt.png" alt="ADSync PoC output showing Domain MEGABANK.LOCAL Username administrator Password d0m@in4dminyeah!" >}}

Domain administrator credentials, handed over by the sync service itself.

### Root

```bash
evil-winrm -i 10.129.228.111 -u administrator -p 'd0m@in4dminyeah!'
```

{{< figure src="/images/htb-monteverde/admin-shell.png" alt="evil-winrm shell as megabank\\administrator on MONTEVERDE" >}}

{{< figure src="/images/htb-monteverde/root-flag.png" alt="impacket-psexec SYSTEM shell on MONTEVERDE showing root.txt flag f84353d55cbbd5786a742b55af30f681" >}}

## Takeaways

**Azure AD Connect is one of the highest-value targets on an AD network.** The sync account needs DCSync rights to function, which means anyone who can decrypt its credentials effectively becomes domain admin. The attack surface is the local MSSQL database where those credentials sit, protected only by DPAPI tied to the machine account.

**Config files in SMB shares are a real finding.** The `azure.xml` file was a leftover from an AD Connect setup - the kind of thing that gets created, used once, and forgotten. Spidering readable shares automatically is worth doing any time you land with SMB access.

**Username-as-password service accounts still happen.** SABatchJobs had no obvious exposure until it handed us an authenticated foothold into an environment running Azure AD Sync.

## References

- [Azure AD Connect DB Exploit - xpnsec](https://blog.xpnsec.com/azuread-connect-for-redteam/)
- [HTB Monteverde - Official](https://app.hackthebox.com/machines/Monteverde)
