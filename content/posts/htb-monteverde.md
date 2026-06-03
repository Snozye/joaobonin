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
  - bloodhound
  - azure-ad-connect
  - privesc
  - write-up
description: "Monteverde is a Medium Windows Active Directory box from HackTheBox. We enumerate domain users via RPC, discover a username-as-password credential for SABatchJobs, find an Azure AD Connect config file containing plaintext credentials in an SMB share, and escalate to Administrator by decrypting the Azure AD Sync service account password from the local MSSQL Express database."
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

RPC null session gives us a user list. A password spray with username=password lands us `SABatchJobs:SABatchJobs`. From there we spider the SMB shares and find `mhope/azure.xml` sitting in the `users$` share - a leftover Azure AD Connect config file with a cleartext password. We spray again and get in as `mhope` via WinRM. Privilege escalation abuses the fact that `mhope` is in the Azure Admins group: we decrypt the ADSync service account credentials from the local MSSQL database using a PowerShell PoC, which hands us domain administrator.

## Recon

Standard nmap kicked things off:

```bash
nmap -sC -sV -oA nmap/monteverde 10.129.228.111
```

{{< figure src="/images/htb-monteverde/nmap.png" alt="nmap scan showing ports 53 88 135 389 445 5985 and others open on a Windows Domain Controller" >}}

This is clearly a Domain Controller - Kerberos on 88, LDAP on 389/636, Global Catalog on 3268/3269, and WinRM on 5985. The LDAP banner confirms the domain as `MEGABANK.LOCAL`. Port 5985 being open is always a good sign; if we find credentials for someone with the right group membership, we can get a shell directly without needing to deal with SMB exec or any of that.

## Enumeration

### User Enumeration

With a DC, the first thing to try is anonymous/null session enumeration. A lot of older AD environments still allow it, and sure enough:

{{< figure src="/images/htb-monteverde/enum-users.png" alt="nxc output listing domain users including SABatchJobs mhope AAD_987d7f and others" >}}

We got a clean user list: `SABatchJobs`, `mhope`, `AAD_987d7f`, `dgalanos`, `roleary`, `smorgan`, plus the usual built-ins. The `AAD_987d7f` account stands out immediately - that naming convention is the Azure AD Connect sync account, which is auto-generated during installation. File that away for later.

### Password Spray - Round 1

With a user list in hand, the classic move is to check whether anyone used their username as their password. netexec makes this easy with `--no-bruteforce`, which pairs each user with their own username as the password:

{{< figure src="/images/htb-monteverde/password-spray-sabatchjobs.png" alt="nxc password spray showing SABatchJobs:SABatchJobs as valid credentials" >}}

`SABatchJobs:SABatchJobs` - a service account using its own name as password. These batch job accounts often get created with a temporary password that nobody ever changes. We're in.

### SMB Shares

Let's see what `SABatchJobs` can reach:

{{< figure src="/images/htb-monteverde/smb-shares.png" alt="SMB share enumeration showing azure_uploads READ users$ READ NETLOGON and SYSVOL accessible" >}}

Interesting shares: `azure_uploads` with READ access, and `users$` also readable. The `azure_uploads` share name is telling - combined with that `AAD_987d7f` account, Azure AD Connect is definitely in play here.

### Spidering for Files

Rather than clicking through shares manually, spider_plus gives us a JSON inventory of everything readable:

{{< figure src="/images/htb-monteverde/spider-plus.png" alt="nxc smb command running spider_plus module against MONTEVERDE" >}}

{{< figure src="/images/htb-monteverde/spider-plus-output.png" alt="spider_plus JSON output showing mhope/azure.xml file in the users$ share" >}}

There it is: `mhope/azure.xml` sitting in the `users$` share, 1.18 KB. An XML file named `azure.xml` in a user's home folder is a very specific kind of red flag.

## Foothold

### Extracting Credentials from azure.xml

Download the file:

{{< figure src="/images/htb-monteverde/azure-xml-download.png" alt="nxc smb command downloading mhope/azure.xml from the users$ share" >}}

{{< figure src="/images/htb-monteverde/azure-xml-content.png" alt="azure.xml contents showing PSADPasswordCredential object with password 4n0therD4y@n0th3r$ for mhope" >}}

Jackpot. The file is a serialized `Microsoft.Azure.Commands.ActiveDirectory.PSADPasswordCredential` PowerShell object - exactly what gets created when someone runs `New-AzADServicePrincipal` or sets up Azure AD Connect credentials via PowerShell and forgets to clean up after themselves. The `<S N="Password">` field is cleartext: `4n0therD4y@n0th3r$`.

### Password Spray - Round 2

We have a password. Time to find out who it belongs to:

{{< figure src="/images/htb-monteverde/mhope-spray.png" alt="nxc smb spray showing mhope:4n0therD4y@n0th3r$ as valid credentials" >}}

`mhope:4n0therD4y@n0th3r$` - the file was in their home folder, so this tracks. And since WinRM (5985) is open, let's check if mhope has remote management access:

```bash
evil-winrm -i 10.129.228.111 -u mhope -p '4n0therD4y@n0th3r$'
```

We're in. User flag:

{{< figure src="/images/htb-monteverde/user-flag.png" alt="WinRM connection as mhope showing user.txt flag 780161b0b1dd87325774901e5b182250" >}}

## Privilege Escalation

### Enumerating mhope's Privileges

Before running BloodHound, a quick group check:

```powershell
Get-ADGroupMember 'Azure Admins'
```

mhope is in `Azure Admins`. That group name, combined with the `ADSync` service running locally, points straight at the Azure AD Connect attack path.

### Collecting AD Data with BloodHound

{{< figure src="/images/htb-monteverde/bloodhound.png" alt="bloodhound-python running as mhope to collect Active Directory data from MEGABANK.LOCAL" >}}

BloodHound confirms mhope's group membership and that the Azure AD Connect sync account (`AAD_987d7f`) has DCSync privileges - because that's how Azure AD Connect works. It needs to replicate password hashes to Azure, so Microsof grants it `DS-Replication-Get-Changes-All`. If we can get that account's credentials, we own the domain.

### Decrypting the Azure AD Connect Password

Azure AD Connect stores the sync account credentials in a local MSSQL Express database (`ADSync`). The data is encrypted using the Windows Data Protection API (DPAPI), which ties the encryption to the local machine account. This means any user who can query the database and has access to the DPAPI key material can decrypt it - and `mhope`, as an Azure Admin, can do exactly that.

There's a well-known PoC for this. On the `evil-winrm` session as mhope, we upload and run it:

```powershell
# Upload the script
upload /opt/AdSyncDecrypt/Get-MSOLDecryptedCredentials.ps1

# Import and run
Import-Module .\Get-MSOLDecryptedCredentials.ps1
Get-MSOLDecryptedCredentials
```

The script connects to the local `localhost\ADSync` SQL instance, pulls the encrypted blob from the `mms_server_configuration` table, and decrypts it using the stored DPAPI key:

```
Username : administrator@megabank.local
Password : d0m@in4dminyeah!
```

Domain administrator credentials, handed to us by the sync service.

### Getting Root

```bash
evil-winrm -i 10.129.228.111 -u administrator -p 'd0m@in4dminyeah!'
```

```powershell
type C:\Users\Administrator\Desktop\root.txt
```

Box complete.

## Takeaways

**Azure AD Connect is a high-value target.** The sync account needs DCSync rights to do its job, which means anyone who can decrypt its credentials effectively becomes a domain admin. The attack surface here is the local MSSQL database where those credentials sit, protected only by DPAPI tied to the machine account.

**Config files in SMB shares are a real finding.** The `azure.xml` file was a leftover from an AD Connect setup - the kind of thing that gets created, used once, and forgotten. Spidering `users$` and `azure_uploads` automatically is worth doing on any machine where you land with low-privilege SMB read access.

**Username-as-password still works.** Service accounts are frequently set up with a temporary password matching the account name, especially when they're meant to be "low privilege." SABatchJobs had no obvious exposure - until it gave us a foothold into an environment running Azure AD Sync.

## References

- [HTB Monteverde - Official](https://app.hackthebox.com/machines/Monteverde)
- [Azure AD Connect Password Extraction - VbScrub](https://github.com/VbScrub/AdSyncDecrypt)
- [Azure AD Connect DB Exploit - Understanding the Attack](https://blog.xpnsec.com/azuread-connect-for-redteam/)
