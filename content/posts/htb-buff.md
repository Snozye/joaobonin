+++
date = '2026-05-19T00:00:00-03:00'
draft = false
title = 'HTB: Buff - OSCP Prep Write-up'
tags = ['htb', 'oscp', 'lain-kusanagi', 'write-up', 'windows', 'web', 'rce', 'bof', 'cloudme', 'chisel']
description = 'Write-up for the HackTheBox machine Buff - chaining an unauthenticated RCE in a gym web app with a local CloudMe buffer overflow to get SYSTEM.'
ShowToc = true
TocOpen = false
[cover]
image = 'images/htb-buff/cover.png'
+++

Two vulnerabilities, zero authentication required for either one. Buff is a good reminder that public exploits sometimes just work - and that internal services running on non-standard ports are always worth the extra look.

## Machine info

| | |
|---|---|
| **Name** | Buff |
| **Platform** | HackTheBox |
| **OS** | Windows |
| **Difficulty** | Easy |

## TL;DR

- Web app running Gym Management System 1.0 is vulnerable to **unauthenticated RCE** (EDB-48506) - drops a webshell and a shell as `buff\shaun`
- Internal port 8888 is running **CloudMe 1.1.12**, accessible only from localhost
- Uploaded **Chisel** for port forwarding, then fired a **buffer overflow exploit** (EDB-48389) against CloudMe to get a SYSTEM shell

---

## Recon

### Nmap

```bash
nmap -sV -sC -Pn 10.129.2.18
```

![Nmap scan showing port 8080 open with Apache httpd 2.4.43 on Windows](/images/htb-buff/nmap-scan.png)

Only port **8080** open - Apache 2.4.43 on Windows with PHP 7.4.6. No SSH, no SMB. Everything goes through the web app.

---

## Enumeration

### Web app fingerprinting

Browsing to port 8080 shows a fitness website called "mrb3n's Bro Hut".

![Gym website homepage](/images/htb-buff/gym-website.png)

The contact page footer is where things get interesting.

![Footer on contact.php showing "Made using Gym Management Software 1.0"](/images/htb-buff/gym-version.png)

**Gym Management System 1.0** - a quick search on Exploit-DB returns a working unauthenticated RCE.

---

## Foothold

### EDB-48506 - Gym Management System 1.0 Unauthenticated RCE

The [exploit](https://www.exploit-db.com/exploits/48506) abuses an unrestricted file upload in the profile picture functionality. No authentication needed - it uploads a PHP webshell and gives interactive command execution.

```bash
python2 exp.py http://10.129.2.18:8080/
```

![Webshell connected, whoami showing buff\shaun](/images/htb-buff/webshell-rce.png)

Shell as `buff\shaun`. User flag in hand.

![type user.txt returning the flag hash](/images/htb-buff/user-flag.png)

---

## Privilege Escalation

### Discovering CloudMe on port 8888

Running `netstat -ano` from the webshell reveals something interesting listening on loopback only.

![netstat output showing 127.0.0.1:8888 LISTENING with PID 9748](/images/htb-buff/netstat-8888.png)

Port 8888, localhost only. Browsing `C:\Users\shaun\Downloads` turns up the culprit.

![dir showing CloudMe_1112.exe, 17.8 MB](/images/htb-buff/cloudme-exe.png)

**CloudMe 1.1.12** - vulnerable to a stack-based buffer overflow: [EDB-48389](https://www.exploit-db.com/exploits/48389).

### Port forwarding with Chisel

CloudMe only accepts connections from localhost, so a tunnel is needed to reach it from Kali.

Upload Chisel to the target via the webshell and start the port forward:

![curl downloading chisel.exe, dir confirming it landed, chisel client tunneling R:8888:127.0.0.1:8888](/images/htb-buff/chisel-portforward.png)

Start the Chisel server on Kali:

![chisel server -p 8001 --reverse, session established, proxy R#8888 listening](/images/htb-buff/chisel-server.png)

Confirm the tunnel is live:

![nmap localhost -p8888 -sV showing tcpwrapped, confirming the forward is active](/images/htb-buff/nmap-tunnel.png)

### EDB-48389 - CloudMe 1.1.12 Buffer Overflow

Generate shellcode for a reverse shell and substitute it into the BOF exploit. Then fire it against the forwarded port:

```bash
python exp2.py
```

![nc listener receiving SYSTEM shell, whoami=buff\administrator, type root.txt](/images/htb-buff/root-shell.png)

SYSTEM. Both flags captured.

---

## Takeaways (for OSCP)

- **Always enumerate internal ports.** `netstat -ano` from a low-privilege shell revealed CloudMe on 8888 - invisible from outside, but critical. Services bound to loopback are often older and less patched.
- **Port forwarding is a core skill.** Chisel, socat, or SSH local forward - have them all ready. Practice the setup until it is muscle memory.
- **Public BOF exploits require shellcode customization.** EDB-48389 ships with placeholder shellcode. You need to regenerate it for your IP/port and verify the exploit targets the correct CloudMe version and offset.

## References

- [HackTheBox - Buff](https://app.hackthebox.com/machines/Buff)
- [EDB-48506 - Gym Management System 1.0 Unauthenticated RCE](https://www.exploit-db.com/exploits/48506)
- [EDB-48389 - CloudMe 1.1.12 Buffer Overflow](https://www.exploit-db.com/exploits/48389)
- [Chisel - Fast TCP/UDP tunnel over HTTP](https://github.com/jpillora/chisel)
- Lain Kusanagi list (OSCP prep)
