+++
date = '2026-04-16T15:26:29-03:00'
draft = true
title = 'Active Directory Attack Chain'
+++

+++
  date = '2026-04-20T18:00:00-03:00'
  draft = false
  title = 'Active Directory Attack Chain: From User to Domain Admin'
  tags = ['red-team', 'active-directory', 'crta', 'bloodhound']
  description = 'Walking through a full AD compromise chain — Kerberoast, lateral movement, DCSync — from a CRTA lab perspective.'
  cover.image = '/images/ad-attack-chain-cover.png'
  ShowToc = true
  +++

  ## TL;DR

  - Kerberoasted a service account to get initial creds
  - Used BloodHound to map the path to Domain Admin
  - Abused DCSync to dump krbtgt and forge a Golden Ticket
  - Enterprise takeaway: monitor for unusual LDAP queries and SPN enumerations

  ## Why this matters
