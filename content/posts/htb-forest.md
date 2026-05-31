---
title: "HTB: Forest"
date: 2026-05-31
draft: false
tags:
  - htb
  - windows
  - easy
  - active-directory
  - smb
  - as-rep-roasting
  - kerberos
  - dcsync
  - bloodhound
  - impacket
  - crackmapexec
  - write-up
description: "Forest is an Easy Windows Active Directory box on HackTheBox. The path goes through AS-REP roasting a service account, then using BloodHound to find a WriteDacl abuse chain through Exchange groups to grant DCSync and dump the domain."
ShowToc: true
cover:
  image: "/images/htb-forest/cover.png"
  alt: "HackTheBox Forest machine cover"
---

Forest is one of those boxes that feels like a guided tour through Active Directory attack fundamentals. No CVEs, no fancy exploits - just proper AD enumeration, a misconfigured service account, and a BloodHound-mapped path straight to domain admin.

## Machine Info

| Field      | Details                        |
|------------|--------------------------------|
| Name       | Forest                         |
| Platform   | HackTheBox                     |
| OS         | Windows                        |
| Difficulty | Easy                           |
| IP         | 10.129.5.64                    |

## TL;DR

SMB user enumeration reveals a service account with no Kerberos pre-auth required. AS-REP roasting gives us a crackable hash. Shell as `svc-alfresco` via WinRM. BloodHound maps a path through Exchange groups giving WriteDacl on the domain. We abuse that to grant DCSync, dump the Administrator hash, and psexec our way to SYSTEM.

## Recon

{{< figure src="/images/htb-forest/nmap.png" alt="nmap scan showing standard Active Directory ports open including 53, 88, 389, 445, 3268, and 5985" >}}

The port list is a dead giveaway: DNS (53), Kerberos (88), LDAP (389), SMB (445), Global Catalog (3268), WinRM (5985). This is a domain controller. The hostname is `FOREST` and the domain is `htb.local`.

## Enumeration

With SMB accessible and no credentials yet, let's see what we can enumerate without auth.

```bash
nxc smb 10.129.5.64 -u '' -p '' --users
```

{{< figure src="/images/htb-forest/users-enum.png" alt="nxc SMB user enumeration showing domain users including svc-alfresco, lucinda, andy, mark, and santi among others" >}}

Anonymous SMB gives us the full user list - this is more common than you'd expect on older AD environments. The interesting account here is `svc-alfresco`. Service accounts often have weaker configurations, and in this case it turns out to have a critical one.

## Foothold

**AS-REP Roasting**

Kerberos pre-authentication is a setting that forces clients to prove they know the account's password before the KDC will hand out a ticket. When it's disabled on an account, anyone can request a ticket for that user and get an encrypted blob back - without knowing the password first. That blob can then be cracked offline.

```bash
impacket-GetNPUsers htb.local/ --no-pass -request -usersfile usersFiltered
```

{{< figure src="/images/htb-forest/asrep-roast.png" alt="impacket-GetNPUsers output showing svc-alfresco AS-REP hash captured for offline cracking" >}}

`svc-alfresco` doesn't have `UF_DONT_REQUIRE_PREAUTH` set (meaning pre-auth IS disabled), so we get a Kerberos AS-REP hash back. John handles the rest.

{{< figure src="/images/htb-forest/hash-crack.png" alt="john cracking the AS-REP hash with rockyou.txt, finding the password s3rvice" >}}

Password: `s3rvice`. WinRM is open on port 5985, let's try it.

{{< figure src="/images/htb-forest/winrm-shell.png" alt="nxc winrm confirming svc-alfresco:s3rvice credentials work with Pwnd exclamation" >}}

We're in.

## Privilege Escalation

**BloodHound Mapping**

With a foothold, the next step is understanding the AD environment. BloodHound is the standard tool for this - it collects relationships between users, groups, computers and GPOs, then maps attack paths.

{{< figure src="/images/htb-forest/bloodhound-collect.png" alt="BloodHound-python collecting Active Directory data from the domain controller" >}}

```bash
bloodhound-python -u 'svc-alfresco' -p 's3rvice' -dc FOREST.htb.local -c all -ns 10.129.5.64 --dns-tcp
```

{{< figure src="/images/htb-forest/bloodhound-graph.png" alt="BloodHound attack path showing svc-alfresco through Service Accounts, Privileged IT Accounts, Account Operators to Exchange Windows Permissions with WriteDacl on HTB.LOCAL domain" >}}

The graph tells a clear story: `svc-alfresco` is a member of `Service Accounts`, which is inside `Privileged IT Accounts`, which gives membership in `Account Operators`. Account Operators can manage most groups - including `Exchange Windows Permissions`. And that group has `WriteDacl` on the `HTB.LOCAL` domain object.

`WriteDacl` on the domain means we can modify the domain's ACL. Specifically, we can grant ourselves DCSync rights - the ability to replicate domain credentials as if we were another domain controller.

**Abusing WriteDacl**

Step one: add `svc-alfresco` to the `Exchange Windows Permissions` group.

{{< figure src="/images/htb-forest/add-to-group.png" alt="net rpc command adding svc-alfresco to Exchange Windows Permissions group and verifying membership" >}}

```bash
net rpc group addmem "Exchange Windows Permissions" "svc-alfresco" \
  -U "htb.local/svc-alfresco%s3rvice" -S 10.129.5.64
```

Step two: use `bloodyad` to grant DCSync rights to our account.

{{< figure src="/images/htb-forest/dcsync-rights.png" alt="bloodyad command granting DCSync rights to svc-alfresco on the htb.local domain" >}}

```bash
bloodyad --host 10.129.5.64 -d htb.local -u svc-alfresco -p s3rvice add dcsync svc-alfresco
```

**DCSync and Pass-the-Hash**

With DCSync rights in place, we can ask the domain controller to replicate the Administrator's credentials to us using `secretsdump`.

{{< figure src="/images/htb-forest/secretsdump.png" alt="secretsdump output dumping the Administrator NTLM hash from the domain controller" >}}

```bash
secretsdump.py htb.local/svc-alfresco:s3rvice@10.129.5.64 -just-dc-user Administrator
```

We have the Administrator NTLM hash. No need to crack it - pass-the-hash with `psexec` gets us a SYSTEM shell directly.

{{< figure src="/images/htb-forest/psexec-system.png" alt="impacket-psexec using the Administrator hash to get a SYSTEM shell and reading root.txt" >}}

```bash
impacket-psexec Administrator@10.129.5.64 -hashes :32693b11e6aa90eb43d32c72a07ceea6
```

`nt authority\system`. Root flag on the desktop.

## Takeaways

**AS-REP roasting is low-hanging fruit in any AD assessment.** Accounts with Kerberos pre-auth disabled hand you a crackable hash with zero credentials. Always run GetNPUsers against any user list you can enumerate.

**BloodHound turns complex AD graphs into actionable paths.** Without it, the chain from `svc-alfresco` through Exchange groups to WriteDacl on the domain would take hours to map manually. With it, it's a five-minute read.

**Exchange-related groups in AD are notorious for overprivileged ACLs.** The `Exchange Windows Permissions` group existing with WriteDacl on the domain is a known design issue left behind by Exchange installations. Even in environments that have removed Exchange, these ACLs often linger.

## References

- [Impacket GetNPUsers](https://github.com/fortra/impacket/blob/master/examples/GetNPUsers.py)
- [BloodyAD](https://github.com/CravateRouge/bloodyAD)
- [BloodHound](https://github.com/BloodHoundAD/BloodHound)
- [Exchange WriteDacl abuse - SpecterOps](https://posts.specterops.io/abusing-exchange-one-api-call-away-from-domain-admin-1e2da1c3da79)
