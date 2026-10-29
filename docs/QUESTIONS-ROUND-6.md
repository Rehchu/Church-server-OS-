# Round 6: the 40 questions, with the answers saved

Your answer for each is in **bold**. To change one, reply with its number and the new answer (for example "14: Syncthing").

## The Macs: setup, removal, care

1. How the server manages the Macs: **A small ariseOS helper**. A launchd helper on each church Mac checks the server every few minutes (church network or Tailscale) and carries out its tasks; no MDM, no Apple certificate
2. A new person on a Mac: **Sign in at any church Mac**. Their Mac profile is made at the login window on first sign-in (the AD bind does this)
3. Which Macs: **Any church Mac**
4. When an account is disabled: **Checked, then removed**. The helper confirms their files are on the server, then deletes their Mac profile and folder on every church Mac, logged
5. A profile unused on one Mac: **Never removed**. Only leaving removes it
6. Retiring a Mac: **A Retire button**. Checks every profile synced, removes it from the domain and the helper; Bradly erases it by hand
7. The Mac admin account: **A hidden server-run admin**. `ariseadmin` on every Mac, its own random password kept on the server for admins, changed every 30 days
8. Staff rights on Macs: **Standard users**
9. The Mac login window: **A list of faces**. Everyone who has used that Mac shows, plus Other…
10. FileVault: **On, keys on the server**. Each Mac's recovery key escrowed to the server, admins only
11. A lost or stolen Mac: **Cut it off**. Disable its computer account, revoke its Tailscale and its Nextcloud sessions; no remote erase
12. macOS updates: **Security overnight**. The helper installs security updates overnight, never during a service, and asks for a restart; major versions wait for Bradly

## Syncing

13. What syncs: **Desktop and Documents**
14. The sync app: **Nextcloud client**. Nextcloud on the server over the home folders and shares (AD sign-in), the desktop client on every Mac: Finder badges, files on demand, versions
15. Conflicts: **Newest wins**. The newer copy keeps the name; the older one goes to that home's Trash on the server (30 days), not deleted
16. Shares on the Mac: **In the Finder sidebar**. Church, department and Shared-with-me folders on demand through Nextcloud's Finder integration
17. Off-site laptops: **Sync over Tailscale**
18. Big files: **Sync everything**. No size limit
19. Phones: **The Nextcloud app**. Over Tailscale; files only, not the server OS
20. Staff passwords and two-step: **On the Mac + the reset page**. Two-step is turned on for them by an admin

## Who uses the closet OS

21. Who uses the closet OS: **All four admins**. Bradly, Kristina, Apostle Bryant, Pastor Vanessa
22. The pastors: **Full admins, as now**
23. Kristina's powers: **The same as Bradly's**. Every admin and system power, sudo without a password included; Claude stays Bradly's (24)
24. Claude for Kristina: **No, Claude stays Bradly's**

## The domain and email

25. The directory name: **ad.arisecenla.com**. Realm AD.ARISECENLA.COM, NetBIOS ARISE (as built)
26. Where the website lives: **Both addresses show it**. Nothing in ariseOS depends on either
27. Who adds the Wix email records: **Bradly**. Docs give him the exact SPF and DKIM records for mail.arisecenla.com
28. Staff addresses: **first.last@ad.arisecenla.com**. Internal, forwarded to personal email

## Firefox and the Macs’ browsers

29. Firefox profiles: **One per admin**. Switched when an admin signs in at the monitor
30. Saved passwords: **On, per admin**
31. Ad blocker: **uBlock Origin**. Installed for every admin
32. Search engine: **Google**
33. Downloads: **The admin's own Downloads**
34. Add-ons: **Admins add any**
35. Web filter: **Malware only**. Firefox's Safe Browsing; nothing else blocked
36. The Macs' browsers: **Certificate + bookmarks**. The church certificate and a Church bookmarks folder in Safari and Chrome, by the helper

## Enrolling Macs and the rest

37. Enrolling a Mac: **One Terminal line**. Shown in the dashboard: joins the domain, installs the helper, Nextcloud, Tailscale and the certificate
38. Printers: **Added by the helper**
39. Nextcloud's web page: **App and web, files only**. Over Tailscale
40. Department logins: **Sync like a person**

## New, after what you said about Active Directory

The server already is your own Active Directory: Samba runs the domain AD.ARISECENLA.COM, so nothing is paid to Microsoft. Only Macs enrolled as church Macs are touched; personal Macs never are.

41. **A church Mac already has local accounts. What happens to each one?** (a) Ask me per account on the Macs page: Convert, Link or Leave alone *(recommended)*; (b) convert them all; (c) link them all.
42. **Convert** means the local account becomes the matching server user (first.last), keeping every file and setting, and syncing from then on. **Link** means it stays a local account with its own password, but its Desktop and Documents sync to a server user. Is that what you want both to mean? (yes / change it)
43. **Should server accounts be added to every church Mac ahead of time**, like Active Directory pushing users to every machine, so they show in the login faces before anyone signs in? (a) everyone on every church Mac *(recommended)*; (b) only on Macs assigned to them; (c) only when they first sign in.
44. **After a conversion, which password?** (a) their server password everywhere *(recommended)*; (b) keep the old local one (that is what Link is for).
