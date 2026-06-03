---
title: "HTB: Blackfield"
date: 2026-06-03
draft: false
tags:
  - htb
  - windows
  - hard
  - write-up
  - active-directory
  - kerberos
  - as-rep-roasting
  - bloodhound
  - pass-the-hash
  - impacket
  - evil-winrm
  - oscp
description: "Blackfield is a Hard Windows Active Directory box from HackTheBox. ASREPRoasting lands the support account, BloodHound reveals a ForceChangePassword path to audit2020, whose forensic SMB share contains an lsass dump. pypykatz extracts svc_backup's hash, and SeBackupPrivilege abuse via wbadmin extracts ntds.dit to dump the domain admin hash."
ShowToc: true
cover:
  image: "/images/htb-blackfield/cover.png"
  alt: "HTB Blackfield machine avatar"
---

Machine #72 on the Lain Kusanagi list. Every step in this box is intentional - no guesswork, just clean AD attack chaining from zero creds to domain admin. One of the better Hard-rated machines for learning the full lifecycle.

## Machine Info

| | |
|---|---|
| **Name** | Blackfield |
| **Platform** | HackTheBox |
| **OS** | Windows |
| **Difficulty** | Hard |
| **IP** | 10.129.229.17 |
| **Domain** | BLACKFIELD.local |

## TL;DR

RID brute via null session gets a user list. ASREPRoast `support`, crack the hash, collect BloodHound data as support. BloodHound shows `support` can `ForceChangePassword` on `audit2020`. Change the password, enumerate SMB - forensic share has an `lsass.zip` in `memory_analysis`. pypykatz extracts `svc_backup`'s NT hash. PTH as svc_backup into WinRM - `SeBackupPrivilege` is enabled. Try SAM dump first (admin hash is stale). Use `wbadmin` to back up and restore `ntds.dit`, dump it with secretsdump, get the real admin hash, PTH to root.

## Recon

{{< figure src="/images/htb-blackfield/nmap.png" alt="nmap showing ports 53 88 135 389 445 3268 5985 open on BLACKFIELD.local domain controller" >}}

Standard DC layout: DNS, Kerberos, LDAP, SMB, WinRM. Domain is `BLACKFIELD.local`. No web app in sight - this is a pure AD engagement.

## Enumeration

### RID Brute - Building a User List

With no credentials and SMB available, a null session RID brute is the first move:

{{< figure src="/images/htb-blackfield/rid-brute.png" alt="nxc smb rid-brute via guest account against BLACKFIELD domain controller" >}}

This pulls the user list by enumerating RIDs anonymously - a technique that works even when anonymous LDAP queries are blocked.

### ASREPRoasting

With a user list, check for accounts with pre-auth disabled:

{{< figure src="/images/htb-blackfield/asrep-hash.png" alt="impacket-GetNPUsers returning an AS-REP hash for support@BLACKFIELD.LOCAL" >}}

`support` has `UF_DONT_REQUIRE_PREAUTH` set. Got the AS-REP hash. `Administrator` and others have their accounts revoked or restricted - only `support` bites.

Crack it:

{{< figure src="/images/htb-blackfield/john-crack.png" alt="john showing support@BLACKFIELD.LOCAL cracked with password #00^BlackKnight" >}}

`#00^BlackKnight`. We have valid creds: `support:#00^BlackKnight`.

### BloodHound

Before touching anything else, map the domain:

{{< figure src="/images/htb-blackfield/bloodhound-collect.png" alt="bloodhound-python collecting all AD data as support from BLACKFIELD.local" >}}

And the key finding:

{{< figure src="/images/htb-blackfield/bloodhound-forcechangepassword.png" alt="BloodHound graph showing SUPPORT has ForceChangePassword edge to AUDIT2020" >}}

`support` can force a password reset on `audit2020` without knowing the current password. `ForceChangePassword` in AD means you hold the `User-Force-Change-Password` extended right on that account - enough to set a new password via MSRPC even without the old one.

### Changing audit2020's Password

`net rpc password` abuses the SAMR protocol to reset the password remotely:

{{< figure src="/images/htb-blackfield/change-password.png" alt="net rpc password changing audit2020 password to newP@ssword2022 as support, then nxc confirming audit2020:newP@ssword2022 works" >}}

`audit2020:newP@ssword2022` confirmed working.

### SMB Enumeration as audit2020

{{< figure src="/images/htb-blackfield/smb-shares.png" alt="nxc smb showing forensic READ and profiles$ READ shares accessible as audit2020" >}}

`forensic` with READ access stands out. The name alone tells you this is worth checking.

### lsass.zip from the Forensic Share

{{< figure src="/images/htb-blackfield/smbclient-lsass.png" alt="smbclient connecting to forensic share as audit2020, navigating to memory_analysis and downloading lsass.zip" >}}

`memory_analysis/lsass.zip`. This is a dump of the LSASS process memory - the Windows component responsible for authentication. It holds every logged-on user's credentials in memory. Time to extract them.

## Foothold

### Extracting Credentials from lsass

Unzip and run pypykatz:

```bash
pypykatz lsa minidump lsass.DMP
```

{{< figure src="/images/htb-blackfield/pypykatz-svc-backup.png" alt="pypykatz MSV section showing svc_backup NT hash 9658d1d1dcd9250115e2205d9f48400d" >}}

`svc_backup` NT hash: `9658d1d1dcd9250115e2205d9f48400d`. The dump also had Administrator:

{{< figure src="/images/htb-blackfield/pypykatz-admin.png" alt="pypykatz MSV section showing Administrator NT hash 7f1e4ff8c6a8e6b6fcae2d9c0572cd62" >}}

Test both hashes via pass-the-hash:

{{< figure src="/images/htb-blackfield/pth-test.png" alt="nxc smb PTH showing Administrator hash 7f1e4ff8 fails with STATUS_LOGON_FAILURE, svc_backup hash 9658d1d1 succeeds" >}}

The Administrator hash from lsass is stale - the password was rotated after the dump was taken. `svc_backup` works. This matters for later.

WinRM is open - confirm access:

{{< figure src="/images/htb-blackfield/winrm-access.png" alt="nxc winrm PTH as svc_backup showing Pwnd on BLACKFIELD domain controller" >}}

```bash
evil-winrm -i 10.129.229.17 -u svc_backup -H 9658d1d1dcd9250115e2205d9f48400d
```

## Privilege Escalation

### SeBackupPrivilege

{{< figure src="/images/htb-blackfield/whoami-priv.png" alt="whoami /priv showing SeBackupPrivilege and SeRestorePrivilege both Enabled for svc_backup" >}}

`SeBackupPrivilege` and `SeRestorePrivilege` both enabled. `SeBackupPrivilege` lets you read ANY file on the system regardless of DACL - it was designed for backup operators to do their job, but it's a perfect privilege escalation vector when you can use it creatively.

{{< figure src="/images/htb-blackfield/user-flag.png" alt="evil-winrm shell as svc_backup showing user.txt 3920bb317a0bef51027e2852be64b543" >}}

### Attempt 1 - SAM + SYSTEM Dump

The first instinct with SeBackupPrivilege is to dump SAM and SYSTEM for local hash extraction:

{{< figure src="/images/htb-blackfield/reg-save.png" alt="reg save HKLM\\SAM and HKLM\\SYSTEM both completing successfully in svc_backup session" >}}

{{< figure src="/images/htb-blackfield/secretsdump-sam.png" alt="impacket-secretsdump SAM dump showing Administrator hash 7f1e4ff8c6a8e6b6fcae2d9c0572cd62 - same stale hash" >}}

Same hash as the lsass dump. The local SAM also has the stale Administrator password. This is a DC - the `Administrator` account's hash in the local SAM isn't what's used for domain authentication. We need `ntds.dit`.

### Getting ntds.dit with wbadmin

`ntds.dit` is locked by the NTDS service while the DC is running - you can't just copy it. SeBackupPrivilege gets around this, and the cleanest approach on this box is `wbadmin`: the Windows Server Backup CLI, which can create volume shadow copies and extract specific files without needing to call `diskshadow` or `vssadmin` directly.

First, back up the `ntds` directory using a loopback UNC path so the backup lands on disk:

{{< figure src="/images/htb-blackfield/wbadmin-backup.png" alt="wbadmin start backup targeting \\127.0.0.1\\c$\\temp including c:\\windows\\ntds, completing successfully" >}}

Then restore just `ntds.dit` from that backup to `C:\temp`:

{{< figure src="/images/htb-blackfield/wbadmin-recovery.png" alt="wbadmin start recovery restoring ntds.dit from the backup version to C:\\temp with notrestoreacl flag" >}}

{{< figure src="/images/htb-blackfield/ntds-extracted.png" alt="ls C:\\temp showing ntds.dit at 18874368 bytes extracted successfully" >}}

18 MB. That's the live directory database - every user's current credential hashes.

Transfer `ntds.dit` and `system.bak` (for the boot key) to Kali, then dump:

{{< figure src="/images/htb-blackfield/secretsdump-ntds.png" alt="impacket-secretsdump of ntds.dit showing Administrator NT hash 184fb5e5178480be64824d4cd53b99ee and all domain hashes" >}}

Administrator NT hash from ntds.dit: `184fb5e5178480be64824d4cd53b99ee`. Different from what lsass had. This is the real current hash.

### Root

{{< figure src="/images/htb-blackfield/root-flag.png" alt="nxc smb PTH as Administrator with hash 184fb5e5 executing type root.txt showing Pwnd and flag 4375a629c7c67c8e29db269060c955cb" >}}

## Takeaways

**lsass hashes can be stale.** The Administrator hash in the lsass dump was from before a password rotation. When PTH fails for an account that should work, it's worth considering whether the cached credential is outdated - especially on boxes that simulate realistic environments where passwords change.

**ForceChangePassword is a lateral movement primitive worth watching for.** It's quieter than a DCSync because it doesn't touch NTDS directly, but it hands you control of the target account instantly. BloodHound surfaces this kind of edge that you'd never find manually.

**SeBackupPrivilege + wbadmin is a cleaner ntds.dit extraction path than diskshadow.** No interaction with VSS admin tools, just a backup job targeting the ntds directory via a loopback share. The `-notrestoreacl` flag on recovery means the file lands accessible even though ntds.dit normally has restricted ACLs.

**ntds.dit always has the current hash, lsass may not.** The NTDS database is the source of truth for domain credentials. If you're on a DC and PTH is failing with hashes from memory, go to the database.

## References

- [wbadmin ntds.dit extraction technique](https://pentestlab.blog/2018/07/04/dumping-domain-password-hashes/)
- [SeBackupPrivilege abuse](https://github.com/giuliano108/SeBackupPrivilege)
- [HTB Blackfield](https://www.hackthebox.com/machines/Blackfield)
