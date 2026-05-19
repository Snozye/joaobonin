+++
date = '2026-05-19T00:00:00-03:00'
draft = false
title = 'HTB: Active - OSCP Prep Write-up'
tags = ['htb', 'oscp', 'lain-kusanagi', 'write-up', 'windows', 'active-directory', 'smb', 'gpp', 'kerberoasting', 'impacket']
description = 'Write-up for the HackTheBox machine Active - GPP credentials buried in the Replication share expose SVC_TGS, and Kerberoasting that account cracks the Administrator password.'
ShowToc = true
TocOpen = false
[cover]
image = 'images/htb-active/cover.png'
+++

GPP credentials. Still out there in the wild. Active is one of those machines that aged into a legend - the technique it teaches was patched in 2014, but the lesson sticks forever. Classic AD box, clean attack path, zero fluff.

## Machine info

| | |
|---|---|
| **Name** | Active |
| **Platform** | HackTheBox |
| **OS** | Windows |
| **Difficulty** | Easy |

## TL;DR

- Anonymous SMB access exposes the Replication share, which contains a `Groups.xml` file with a GPP-encrypted password for `SVC_TGS`
- `gpp-decrypt` recovers the plaintext: `GPPstillStandingStrong2k18`
- Authenticated as `SVC_TGS`, the Users share is readable - user flag sitting in `SVC_TGS\Desktop`
- Kerberoasting as `SVC_TGS` returns an Administrator TGS ticket; John cracks it to `Ticketmaster1968`
- `impacket-psexec` with Administrator creds gives a SYSTEM shell

---

## Recon

### Port scan

The scan reveals a textbook Domain Controller fingerprint - DNS on 53, RPC on 135 and 593, SMB on 445, LDAP Global Catalog on 3269, Active Directory Web Services on 9389, and a pile of dynamic RPC ports in the high range.

![Port scan results showing open DC ports](/images/htb-active/nmap-scan.png)

Lots of ports, but the story here is clear: **SMB on 445**. On a DC with no web server visible, SMB is almost always the first thing worth touching.

---

## Enumeration

### Anonymous SMB - the Replication share

First question when hitting SMB on a DC: can I list shares without credentials?

![Anonymous SMB enumeration showing Replication share with READ access](/images/htb-active/smb-anon-shares.png)

The `Replication` share allows anonymous READ access. The standard admin shares (`ADMIN$`, `C$`, `IPC$`) are there as expected. `Replication` is the odd one out - it maps to a copy of the SYSVOL replication data and should not be world-readable.

### Crawling the share with spider_plus

`nxc`'s `spider_plus` module walks a share recursively and saves a JSON map of every file it finds - paths, sizes, and timestamps. Useful for quickly surveying large shares without downloading everything blindly.

![spider_plus crawling the Replication share and saving metadata](/images/htb-active/smb-spider-replication.png)

The module saved its output to a JSON file. Opening it, one path stands out immediately:

![JSON metadata showing Groups.xml path inside the Policies folder](/images/htb-active/groups-xml-found.png)

`active.htb/Policies/{31B2F340-016D-11D2-945F-00C04FB984F9}/MACHINE/Preferences/Groups/Groups.xml`

That path structure - a GPO GUID, then `MACHINE/Preferences/Groups/Groups.xml` - is a classic sign of Group Policy Preferences (GPP) credentials. Worth downloading immediately.

### Groups.xml - the GPP vulnerability explained

Group Policy Preferences was a feature introduced in Windows Server 2008 that allowed admins to push local user account settings (including passwords) via Group Policy. The passwords were stored AES-256 encrypted in `Groups.xml` files that lived in SYSVOL - readable by any domain-authenticated user, and often readable anonymously when Replication shares are misconfigured like this one.

The problem: Microsoft published the static AES encryption key in their own MSDN documentation (MS14-025). Once that key is public, every `cpassword` field in every `Groups.xml` across the internet is trivially decryptable. Microsoft patched this in May 2014 by removing the ability to set new GPP passwords, but any credentials stored before that patch remained sitting there - cleartext-equivalent, waiting.

![cat Groups.xml showing SVC_TGS username and cpassword hash](/images/htb-active/groups-xml-content.png)

There it is: `userName="active.htb\SVC_TGS"` with a `cpassword` field containing the AES-encrypted value. This file was last modified in 2018 - four years after the patch, still unrotated.

### Decrypting with gpp-decrypt

`gpp-decrypt` takes the `cpassword` value and spits out the plaintext using that published key:

![gpp-decrypt output showing GPPstillStandingStrong2k18](/images/htb-active/gpp-decrypt.png)

Credentials: `SVC_TGS:GPPstillStandingStrong2k18`. The password is a self-aware jab at how long this technique stayed viable.

---

## Foothold

### Authenticated SMB enumeration

With valid creds in hand, let's see what `SVC_TGS` can actually reach:

![nxc SMB authenticated as SVC_TGS showing additional readable shares](/images/htb-active/smb-svc-tgs-shares.png)

Now `NETLOGON`, `Replication`, `SYSVOL`, and `Users` are all readable. The `Users` share maps to `C:\Users` on the DC - that is where the flags live.

### Grabbing user.txt via smbclient

![smbclient connected to Users share showing home directories](/images/htb-active/smb-users-share.png)

Browsing to `SVC_TGS\Desktop`:

![Desktop listing showing user.txt](/images/htb-active/user-flag-desktop.png)

`get user.txt` and read it locally:

![cat user.txt showing the user flag](/images/htb-active/user-flag.png)

User flag captured.

---

## Privilege Escalation

### Kerberoasting the Administrator

Having valid domain credentials opens up Kerberoasting. Here is how it works: in Kerberos, any authenticated domain user can request a Ticket Granting Service (TGS) ticket for any Service Principal Name (SPN) registered in Active Directory. Those tickets are encrypted using the NTLM hash of the service account that owns the SPN. If you can get the ticket offline, you can attempt to crack the encryption and recover the plaintext password.

The key detail: you do not need admin rights to request these tickets. Any authenticated domain user qualifies. So the moment you land valid credentials on an AD machine, checking for Kerberoastable accounts costs nothing.

`impacket-GetUserSPNs` requests all available TGS tickets from the DC:

![GetUserSPNs output showing Administrator TGS hash](/images/htb-active/kerberoasting.png)

The `Administrator` account has a registered SPN - and its TGS hash just landed in the terminal. This is genuinely unusual in the real world: having the built-in Administrator account register an SPN is a misconfiguration that rarely happens in production. Here it makes this machine a perfect clean-room demonstration of the technique.

### Cracking the ticket with John

![John cracking the Administrator TGS hash, 1 password cracked](/images/htb-active/john-cracked.png)

Cracked: `Ticketmaster1968`. Rockyou finds it in seconds.

### SYSTEM via psexec

![impacket-psexec connecting as Administrator and landing a SYSTEM shell](/images/htb-active/psexec-system.png)

SYSTEM. `impacket-psexec` works by uploading a service binary to `ADMIN$`, registering it as a Windows service, starting it, and catching the reverse shell. The result runs as `NT AUTHORITY\SYSTEM`.

![type root.txt showing the root flag](/images/htb-active/root-flag.png)

Done.

---

## Takeaways (for OSCP)

- **GPP credentials (MS14-025) are a must-know.** If you see a `Groups.xml` inside a Policies folder on any SMB share, open it. `gpp-decrypt` takes 2 seconds. The technique is patched but old boxes - and real legacy environments - still have these credentials unrotated and waiting.
- **Anonymous SMB enumeration is always step one on Windows.** `nxc smb ... -u '' -p '' --shares` costs nothing and sometimes hands you a foothold before you have done anything else.
- **Kerberoasting requires only a valid domain account.** You do not need admin rights to request TGS tickets. Any authenticated user works. The moment you land credentials on an AD box, run `GetUserSPNs` and see what comes back.
- **Service accounts with weak passwords are the real Kerberoasting target.** In this box it happens to be the built-in `Administrator` account, which is unusual. In real environments you are more likely to find `svc_sql`, `svc_iis`, or similar service accounts - the cracking workflow is identical, the impact varies by what that account can reach.

## References

- [HackTheBox - Active](https://app.hackthebox.com/machines/Active)
- [MS14-025 - Group Policy Preferences Password Vulnerability](https://docs.microsoft.com/en-us/security-updates/securitybulletins/2014/ms14-025)
- [Impacket - GetUserSPNs](https://github.com/fortra/impacket/blob/master/examples/GetUserSPNs.py)
- [Kerberoasting - HackTricks](https://book.hacktricks.xyz/windows-hardening/active-directory-methodology/kerberoast)
- Lain Kusanagi list (OSCP prep)
