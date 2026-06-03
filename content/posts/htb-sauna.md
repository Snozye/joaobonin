---
title: "HTB: Sauna"
date: 2026-06-03
draft: false
tags:
  - htb
  - windows
  - easy
  - write-up
  - active-directory
  - kerberos
  - as-rep-roasting
  - dcsync
  - bloodhound
  - pass-the-hash
  - credential-reuse
  - impacket
  - evil-winrm
  - oscp
description: "ASREPRoasting a bank employee, cracking their hash, then following a chain of autologon credentials and DCSync rights to own the domain."
ShowToc: true
cover:
  image: "/images/htb-sauna/cover.png"
  alt: "HTB Sauna machine avatar"
---

Sauna is an Easy Windows box from HackTheBox built around a classic Active Directory attack chain. From open-source name enumeration to ASREPRoasting, autologon credential exposure, and a DCSync to finish it off - this one hits all the fundamentals.

## Machine Info

| | |
|---|---|
| **Name** | Sauna |
| **Platform** | HackTheBox |
| **OS** | Windows |
| **Difficulty** | Easy |
| **IP** | 10.129.95.180 |

## TL;DR

Scraped employee names off the bank's "About" page, ran them through `username-anarchy` to generate AD-style usernames, and ASREPRoasted `fsmith` whose account had Kerberos pre-auth disabled. Cracked the hash with `rockyou.txt` and logged in via WinRM. Found autologon credentials for `svc_loanmanager` stored in plaintext in the registry. BloodHound showed that account has DCSync rights over the domain - used `secretsdump` to pull the Administrator hash and `psexec` to get SYSTEM.

## Recon

A port scan revealed this is a Windows domain controller - the combination of Kerberos (88), LDAP (389/636), Global Catalog (3268/3269), DNS (53), SMB (445), and WinRM (5985) makes that obvious at a glance.

{{< figure src="/images/htb-sauna/nmap.png" alt="port scan results showing ports 53, 80, 88, 135, 139, 389, 445, 593, 636, 3268, 5985 open on 10.129.95.180" >}}

Port 80 also being open means there is a web app to look at. Good - LDAP enumeration without credentials often hits a wall, so any extra attack surface is welcome.

## Enumeration

### Web - Employee Name Harvesting

The site is for "Egotistical Bank." The home page is mostly fluff, but the `/about` page is the jackpot:

{{< figure src="/images/htb-sauna/about-page.png" alt="Egotistical Bank about page listing team members: Fergus Smith, Hugo Bear, Steven Kerb, Shaun Coins, Bowie Taylor, Sophie Driver" >}}

Six employees listed with full names. In an Active Directory environment, full names are just username wordlists waiting to be formatted. I wrote them to a file:

{{< figure src="/images/htb-sauna/users-list.png" alt="text file listing six full names: Fergus Smith, Hugo Bear, Steven Kerb, Shaun Coins, Bowie Taylor, Sophie Driver" >}}

### Generating Usernames

AD sysadmins pick all kinds of username formats - `fsmith`, `fergus.smith`, `f.smith`, `smithf`, etc. `username-anarchy` automates generating all the common variations from a list of full names:

{{< figure src="/images/htb-sauna/username-anarchy.png" alt="username-anarchy -i users generating username variations, showing 'fergus' as the first result" >}}

This gives a clean wordlist of plausible AD usernames to test.

### Quick Sanity Check - Username as Password

Before anything Kerberos-related, it is worth checking whether anyone has their username set as their password. It takes about five seconds and occasionally pays off:

{{< figure src="/images/htb-sauna/nxc-username-password.png" alt="nxc smb command testing username=password login with --no-brute flag against SAUNA" >}}

Nothing. But worth the try.

### ASREPRoasting

Here is where it gets interesting. Kerberos requires clients to prove they know a user's password before the domain controller issues a ticket-granting ticket (TGT) - this is called **pre-authentication**. If an account has pre-auth disabled, you can ask the DC for an AS-REP for that user without knowing their password. The response will contain a chunk of data encrypted with a key derived from the user's password - which you can crack offline.

`impacket-GetNPUsers` does exactly this: it takes a list of usernames, queries the DC for each one, and hands back any AS-REP hashes it gets:

{{< figure src="/images/htb-sauna/asrep-hash.png" alt="impacket-GetNPUsers returning a Kerberos 5 AS-REP hash for fsmith at EGOTISTICAL-BANK.LOCAL" >}}

`fsmith` - Fergus Smith - has pre-authentication disabled. Got the hash.

## Foothold

Cracked it with `john` against `rockyou.txt`:

{{< figure src="/images/htb-sauna/john-crack.png" alt="john cracking the AS-REP hash, revealing the password Thestrokes23 for fsmith" >}}

`Thestrokes23`. Alright, Fergus.

WinRM was open on port 5985, so I verified it first:

{{< figure src="/images/htb-sauna/winrm-access.png" alt="nxc winrm confirming EGOTISTICAL-BANK.LOCAL\\fsmith:Thestrokes23 grants access - Pwnd!" >}}

Then connected:

```bash
evil-winrm -i 10.129.95.180 -u fsmith -p Thestrokes23
```

Shell as `fsmith`.

## Privilege Escalation

### Autologon Credentials in the Registry

Windows can be configured to automatically log in a user at boot - useful for kiosks or service accounts, dangerous when the password is sitting in plaintext in the registry. The key to check is `HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon`:

{{< figure src="/images/htb-sauna/autologon-creds.png" alt="registry query output showing DefaultUserName as EGOTISTICAL-BANK\\svc_loanmanager and DefaultPassword in plaintext" >}}

`EGOTISTICAL-BANK\svc_loanmanager` with its password sitting right there. Whoever configured this autologon left a loaded gun in the registry.

### BloodHound - Mapping the Path to Domain Admin

Before running anything with the new account, I threw the domain into BloodHound to see what `svc_loanmanager` can actually do:

{{< figure src="/images/htb-sauna/bloodhound-dcsync.png" alt="BloodHound graph showing SVC_LOANMGR has GetChanges and GetChangesAll edges pointing to the EGOTISTICAL-BANK.LOCAL domain object" >}}

`GetChanges` + `GetChangesAll` on the domain object. That means `svc_loanmanager` can perform a **DCSync** attack.

DCSync abuses the `MS-DRSR` replication protocol - the same protocol domain controllers use to sync credential data with each other. An account with both `GetChanges` and `GetChangesAll` rights can impersonate a DC and request credential replication from the real one. The result is every user's NTLM hash in the domain, including the Administrator, without ever touching `LSASS`.

### DCSync - Dumping the Administrator Hash

```bash
secretsdump.py egotistical-bank/svc_loanmgr@10.129.7.11 --just-dc-user Administrator
```

{{< figure src="/images/htb-sauna/secretsdump.png" alt="impacket secretsdump DCSync output showing the Administrator NTLM hash for EGOTISTICAL-BANK.LOCAL" >}}

Administrator hash in hand. No need to crack it - pass-the-hash works just fine.

### SYSTEM

{{< figure src="/images/htb-sauna/psexec-system.png" alt="impacket-psexec shell with Administrator pass-the-hash showing whoami as nt authority\\system on SAUNA" >}}

`nt authority\system`.

{{< figure src="/images/htb-sauna/root-flag.png" alt="root.txt on Administrator desktop: 4df00d92f8d9f04f701c2eee31b266b9" >}}

## Takeaways

**ASREPRoasting is a zero-credential attack.** You don't need to already be authenticated to pull AS-REP hashes - just a list of valid usernames. And valid usernames are often sitting on the company website. Always check for pre-auth disabled accounts when you have any kind of username list.

**Autologon credentials in the registry are a common misconfiguration.** Admins configure service accounts for automatic login and forget the password is in plaintext under `HKLM\...\Winlogon`. It should be one of the first things you check after getting a foothold on a Windows machine.

**DCSync is effectively domain compromise.** Once you have `GetChanges` + `GetChangesAll` on the domain object, it's over. BloodHound is indispensable for finding these privilege paths - manually tracing AD ACLs across thousands of objects is not realistic.

## References

- [impacket-GetNPUsers (ASREPRoast)](https://github.com/fortra/impacket/blob/master/examples/GetNPUsers.py)
- [impacket-secretsdump (DCSync)](https://github.com/fortra/impacket/blob/master/examples/secretsdump.py)
- [username-anarchy](https://github.com/urbanadventurer/username-anarchy)
- [BloodHound](https://github.com/BloodHoundAD/BloodHound)
- [HTB Sauna](https://www.hackthebox.com/machines/Sauna)
