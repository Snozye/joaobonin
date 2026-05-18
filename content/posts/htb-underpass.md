+++
date = '2026-05-18T00:00:00-03:00'
draft = false
title = 'HTB: Underpass - OSCP Prep Write-up'
tags = ['htb', 'oscp', 'lain-kusanagi', 'write-up', 'linux', 'snmp', 'radius', 'daloradius', 'mosh', 'gtfobins', 'sudo']
description = 'Write-up for the HackTheBox machine Underpass - SNMP enumeration reveals a RADIUS server, daloRADIUS with default creds exposes an MD5 hash, and mosh-server sudo escalates to root.'
ShowToc = true
TocOpen = false
[cover]
image = 'images/htb-underpass/cover.png'
+++

HTTP gave nothing. The real entry point was hiding on UDP - a reminder that TCP-only scans miss half the attack surface.

## Machine info

| | |
|---|---|
| **Name** | Underpass |
| **Platform** | HackTheBox |
| **OS** | Linux |
| **Difficulty** | Easy |

## TL;DR

- UDP scan reveals SNMP and RADIUS; SNMP walk with the `public` community string leaks hostname and username
- daloRADIUS web interface accessible with default credentials (`administrator:radius`)
- User `svcMosh` has an MD5 password hash in the RADIUS database - John cracks it
- SSH as svcMosh, `sudo -l` shows `mosh-server` without a password - run it as root and connect with `mosh-client` to get a root shell

---

## Recon

### Nmap TCP

```bash
nmap -sV -sC -Pn -A 10.129.231.213
```

![Nmap TCP results](/images/htb-underpass/nmap-scan.png)

Ports 22 (SSH) and 80 (HTTP). Apache 2.4.52. The web page is the default Apache placeholder - nothing on TCP to work with.

### UDP scan

```bash
nmap -sU 10.129.231.213 --top-ports=100
```

![UDP scan showing SNMP and RADIUS ports](/images/htb-underpass/udp-scan.png)

Port **161/UDP (SNMP)** is open alongside RADIUS ports (1812, 1813). Worth enumerating.

---

## Enumeration

### SNMP - leaking hostname and username

```bash
onesixtyone -c /usr/share/seclists/Discovery/SNMP/common-snmp-community-strings.txt 10.129.231.213
snmpwalk -c public -v1 10.129.231.213
```

![SNMP community scan and walk output](/images/htb-underpass/snmp-discovery.png)

The `public` community string works. The walk returns the system description (`Linux underpass`) and a contact field: `steve@underpass.htb`. Add `underpass.htb` to `/etc/hosts`.

### daloRADIUS - default credentials

daloRADIUS is a web management application for FreeRADIUS servers, providing a browser-based interface to manage users, NAS devices, billing, and reporting. Searching for its default login path reveals it sits at `/daloradius/app/operators/login.php`. Default credentials `administrator:radius` work straight away:

![daloRADIUS dashboard after login](/images/htb-underpass/daloradius-dashboard.png)

### Database credentials and user hash

Under Config -> Database Settings:

![Database settings page](/images/htb-underpass/db-settings.png)

DB user `steve`, password `testing123` - noted. More useful right now: under Management -> Users, there is a user `svcMosh` whose password field holds a raw MD5 hash:

![svcMosh user with MD5 hash](/images/htb-underpass/svcmosh-hash.png)

Hash: `412DD4759978ACFCC81DEAB01B382403`

### Cracking the hash

```bash
john hash --format=Raw-MD5 --wordlist=/usr/share/wordlists/rockyou.txt
```

![John cracking the MD5 hash to underwaterfriends](/images/htb-underpass/john-crack.png)

Cracked: `underwaterfriends`.

---

## Foothold

### SSH as svcMosh

```bash
ssh svcMosh@underpass.htb
```

![SSH login as svcMosh](/images/htb-underpass/ssh-svcmosh.png)

---

## Privilege Escalation

### GTFOBins: mosh-server

```bash
sudo -l
```

![sudo -l showing mosh-server without password](/images/htb-underpass/sudo-l.png)

`svcMosh` can run `/usr/bin/mosh-server` as root without a password. Mosh (mobile shell) is a UDP-based replacement for SSH designed to handle roaming and intermittent connectivity. The server component starts a session, prints a connection key and port, then detaches. Critically - it executes as whatever user invoked it.

Running it as root:

![sudo mosh-server output with MOSH_KEY and port](/images/htb-underpass/sudo-mosh-server.png)

```bash
sudo mosh-server
```

The server prints `MOSH CONNECT 60001 <KEY>` and detaches. Take that key and connect from the attacker machine:

![mosh-client connecting with MOSH_KEY](/images/htb-underpass/mosh-client-connect.png)

```bash
MOSH_KEY=3TmXE+cnsyvbHeBliolucg mosh-client 10.129.231.213 60001
```

![Root shell reading root.txt](/images/htb-underpass/root-shell.png)

Root shell.

---

## Takeaways (for OSCP)

- **Always run a UDP scan.** SNMP (161), TFTP (69), and RADIUS (1812) live on UDP and are invisible to TCP-only scans. On OSCP machines, UDP findings are often the intended entry point.
- **SNMP with the `public` community string is still common.** A walk can leak hostnames, usernames, software versions, and running processes - treat it like free enumeration.
- **Default credentials on internal management tools are almost guaranteed.** daloRADIUS, phpMyAdmin, Grafana, Nagios - check the docs for defaults before anything else.
- **Niche sudo binaries are still covered by GTFOBins.** `mosh-server` is not an obvious privesc tool, but anything that can run as root and spawns a shell is exploitable.

## References

- [HackTheBox - Underpass](https://app.hackthebox.com/machines/Underpass)
- [daloRADIUS - GitHub](https://github.com/lirantal/daloradius)
- [GTFOBins - mosh-server](https://gtfobins.github.io/gtfobins/mosh-server/)
- Lain Kusanagi list (OSCP prep)
