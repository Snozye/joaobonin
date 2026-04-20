+++
date = '2026-04-19T00:00:00-03:00'
draft = false
title = 'HTB: Markup - OSCP Prep Write-up'
tags = ['htb', 'oscp', 'lain-kusanagi', 'write-up', 'windows', 'web', 'xxe', 'ssh']
description = 'Write-up for the HackTheBox machine Markup - part of my OSCP preparation journey following the Lain Kusanagi list.'
ShowToc = true
TocOpen = false

[cover]
image = 'images/htb-markup/cover.png'
+++

Markup is done. A Very Easy Windows box, but with a solid lesson on XXE injection - from discovering the vulnerability to weaponizing it for file read and SSH key extraction. Clean privesc through AutoLogon credentials found by WinPEAS.

## Machine info

| | |
|---|---|
| **Name** | Markup |
| **Platform** | HackTheBox |
| **OS** | Windows |
| **Difficulty** | Very Easy |

## TL;DR

- Login with default credentials `admin:password`
- Order form submits XML - vulnerable to **XXE injection**
- XXE with PHP wrapper to read `process.php` source and confirm the vulnerability
- Extract Daniel's SSH private key via XXE
- WinPEAS finds **AutoLogon credentials** for Administrator

---

## Recon

### RustScan + Nmap

```bash
rustscan -a 10.129.95.192 -- -sV -sC -Pn -A
```

![RustScan results](/images/htb-markup/rustscan.png)

Open ports: **22** (SSH), **80** (HTTP) and **443** (HTTPS).

- **Port 22**: OpenSSH
- **Port 80**: Apache 2.4.41 (Win64) with PHP 7.2.28
- **Port 443**: HTTPS - returned a Bad Request (Error 400) when accessed directly

![Port 443 Bad Request](/images/htb-markup/port443-bad-request.png)

### Web service

Port 80 shows a login page:

![Login page](/images/htb-markup/login-page.png)

Tried `admin:password` and it worked. But I continued with the enumeration.

---

## Enumeration

### Directory brute force

Feroxbuster revealed a few paths:

![Feroxbuster results](/images/htb-markup/feroxbuster-results.png)

Discovered the site uses **XAMPP**:

![XAMPP forbidden](/images/htb-markup/xampp-forbidden.png)

Nothing else interesting. Got back to the logged-in application.

### Exploring the application

After logging in, the app is a delivery store:

![Home page](/images/htb-markup/home-page.png)

The **Order** page has a form that submits orders:

![Order form](/images/htb-markup/order-form.png)

### Source code analysis

Analyzing the source code, I found an HTML comment revealing a username - **Daniel**:

![Source code - Daniel](/images/htb-markup/source-daniel.png)

```html
<!--Modified by Daniel : UI-Fix-9092-->
```

### Intercepting the request

I submitted an order and intercepted the request with Burp. The body is **XML**:

![Burp XML request](/images/htb-markup/burp-xml-request.png)

Content-Type is `text/xml` and the body contains an XML structure with `<order>`, `<quantity>`, `<item>`, and `<address>` tags. This looks like a potential **XXE** (XML External Entity) injection target.

---

## Foothold

### XXE injection

XXE (XML External Entity) injection is a vulnerability that allows an attacker to interfere with an application's processing of XML data. By defining an external entity, an attacker can read files from the server, perform SSRF, or in some cases achieve RCE. More details at [PortSwigger's XXE guide](https://portswigger.net/web-security/xxe#exploiting-xxe-to-retrieve-files).

### Attempt 1: file:// protocol

Since the site uses XAMPP, I tried reading `process.php` using the `file://` protocol:

![XXE file attempt](/images/htb-markup/xxe-file-attempt.png)

The request was processed correctly ("Your order has been processed"), but no file content was returned. The XXE was working but `process.php` contains characters that break XML parsing (`<`, `>`, `&`), so the content couldn't be returned inline.

### Attempt 2: PHP wrapper

Using the `php://filter` wrapper with base64 encoding did the trick - it encodes the file content to avoid XML-breaking characters:

![XXE with PHP wrapper](/images/htb-markup/xxe-php-wrapper.png)

Decoding the base64 response confirmed the XXE and revealed the `process.php` source code:

![process.php source](/images/htb-markup/process-php-source.png)

### Extracting Daniel's SSH key

Since the host has an SSH port open and we know the username **Daniel**, I tried to retrieve his SSH private key via XXE:

![XXE SSH key](/images/htb-markup/xxe-ssh-key.png)

Got the key. Saved it locally and connected:

```bash
chmod 600 id_rsa
ssh daniel@10.129.95.192 -i id_rsa
```

### Shell as Daniel

![Shell as Daniel](/images/htb-markup/shell-daniel.png)

We're in as `daniel` on a Windows machine.

---

## Privilege Escalation

### WinPEAS - AutoLogon credentials

I ran WinPEAS for enumeration and it found **AutoLogon credentials**:

![WinPEAS AutoLogon](/images/htb-markup/winpeas-autologon.png)

```
DefaultUserName    : Administrator
DefaultPassword    : Yhk}QE&j<3M
```

### SSH as Administrator

```bash
ssh Administrator@10.129.95.192
```

![SSH as Administrator](/images/htb-markup/ssh-admin.png)

**Root!**

---

## Takeaways (for OSCP)

- **Always try default credentials first.** `admin:password` is trivial but it got us in. Don't overthink it.
- **XML in requests = check for XXE.** Whenever you see `Content-Type: text/xml` or XML bodies in Burp, test for XXE immediately.
- **PHP wrappers bypass XML parsing issues.** When `file://` doesn't return content because of special characters, use `php://filter/convert.base64-encode/resource=` to get the file as base64.
- **Source code comments leak information.** The `<!--Modified by Daniel-->` comment gave us the username to target for SSH key extraction.
- **WinPEAS finds AutoLogon creds.** On Windows machines, always check for stored credentials - AutoLogon is a common privesc path.

## References

- [HackTheBox - Markup](https://app.hackthebox.com/machines/Markup)
- [PortSwigger - XXE Injection](https://portswigger.net/web-security/xxe)
- Lain Kusanagi list (OSCP prep)
