# Questions for Bradly

Fifty-two questions, multiple choice. Pick a letter; add a word if none fits.
The letter marked *(assumed)* is what the plan uses until you answer. The
questions marked **(before wipe)** change what the installer does on day 1
(docs/SETUP-GUIDE.md § 3); the rest can wait until that part comes up.
Bradly brings the Dell and Synology details on Sunday.

Answer format that works: `1b 2a 3c …` in one message.

---

## The OptiPlex and the Synology

1. **OptiPlex model and RAM** *(before wipe)*
   a. 4 GB or less · b. 8 GB *(assumed)* · c. 16 GB · d. 32 GB or more. Add the model from the sticker (e.g. "7050 SFF").
   Under 8 GB, Guacamole and Vaultwarden leave the day-1 plan.

2. **Drives in it** *(before wipe)*
   a. one spinning disk · b. one SSD *(assumed)* · c. SSD plus a spinning disk · d. two SSDs.
   With one small disk, home folders go on the Synology instead.

3. **Room for another drive**
   a. a free bay or M.2 slot · b. no room · c. not sure *(assumed)*.

4. **Synology model and RAID** *(before wipe)*
   a. SHR *(assumed)* · b. SHR-2 · c. RAID 5 · d. RAID 1 or no RAID. Add the model and the drive sizes.

5. **What is on the Synology now**
   a. nothing yet · b. data that stays where it is *(assumed)* · c. data that can move · d. not sure.

6. **Synology address and login** *(before wipe)*
   a. static IP and I know the DSM admin password *(assumed)* · b. static IP, password unknown · c. gets its address from DHCP · d. not sure.

7. **When the server moves to the Hub, the Synology**
   a. moves with it *(assumed)* · b. stays at Pineville · c. undecided.
   If it stays, nightly backups cross the VPN and home folders are slow at the Hub.

8. **UPS (battery backup)**
   a. Pineville has one · b. the Hub will have one · c. both · d. neither yet *(assumed)*.

9. **The closet**
   a. cool, with a network cable *(assumed)* · b. cool, Wi-Fi only · c. gets hot · d. not sure.

## The Pineville network and the Cisco

10. **The Cisco** *(before wipe)*
    a. Cisco Business (CBS) *(assumed)* · b. Catalyst · c. Small Business SG · d. Meraki · e. not sure, I will photograph the sticker.

11. **The switch login**
    a. I have it *(assumed)* · b. someone else has it · c. nobody knows it.

12. **Networks today** *(before wipe)*
    a. one flat network plus a guest Wi-Fi *(assumed)* · b. separate VLANs already set up · c. several routers, each its own network · d. not sure. Add the subnet if you know it (192.168.1.x, 10.0.0.x).

13. **The router**
    a. the ISP's modem-router box *(assumed)* · b. a separate router (Ubiquiti, Netgear, Cisco) · c. not sure.

14. **Who hands out IP addresses**
    a. the router *(assumed)* · b. the Cisco · c. a separate server or firewall · d. not sure.

15. **Pineville internet**
    a. under 20 Mbit/s upload *(assumed)* · b. 20 to 50 · c. over 50 · d. not sure. Add the ISP name.

16. **Public IP**
    a. dynamic, and I can forward a port *(assumed)* · b. static · c. cannot forward ports (CGNAT or ISP-locked) · d. not sure.

17. **Sunday guest Wi-Fi**
    a. separate network, its own VLAN · b. separate name, same network *(assumed)* · c. guests use the staff Wi-Fi · d. no guest Wi-Fi.

18. **Cameras, thermostat, door locks**
    a. on the same network as the office Macs *(assumed)* · b. on their own network · c. none of these exist · d. not sure.

## Alexandria

19. **What is at Alexandria today**
    a. two or three Macs and a printer *(assumed)* · b. Macs and PCs and a check-in station · c. almost nothing yet · d. not sure.

20. **Alexandria internet**
    a. ISP box, upload unknown *(assumed)* · b. known upload speed (add it) · c. no internet yet.

21. **A spot for a small always-on box next to the router**
    a. yes, with power *(assumed)* · b. yes, if I add a UPS · c. no.

22. **Livestream from Alexandria**
    a. occasionally *(assumed)* · b. every service · c. never.

## People and accounts

23. **Username rule**
    a. first initial plus surname, first names where already used *(assumed)* · b. first names only · c. first.last · d. something else.

24. **Who gets an account**
    a. you will send a list with roles (admin, staff, leadership, media, volunteer) · b. staff and media only for now · c. everyone with a church email.
    No names will be invented; this one needs the list.

25. **Admins besides you**
    a. only me *(assumed)* · b. one more person, dashboard only · c. one more person with SSH too.

26. **Password expiry**
    a. never, 12 characters minimum, lockout after 10 failures *(assumed)* · b. every 90 days · c. every year.

27. **Volunteers**
    a. a home folder each *(assumed)* · b. a login only, for shared machines · c. no accounts for volunteers.

28. **Kids check-in station**
    a. a Windows PC with a shared login *(assumed)* · b. an iPad · c. a Mac · d. none yet.

29. **A shared church Google account (for Tailscale, the daily note, the YouTube token)**
    a. exists, and one other person knows the password *(assumed)* · b. exists, only I know it · c. does not exist yet.

## Macs and PCs

30. **Macs across all three sites**
    a. up to five · b. six to ten *(assumed)* · c. more than ten. Add the oldest macOS version if you know it.

31. **Windows PCs**
    a. none · b. a few, all Windows Pro *(assumed)* · c. some are Windows Home (cannot join a domain) · d. not sure which edition.

32. **Local users on the existing Macs**
    a. one person per login, except the media Mac *(assumed)* · b. several people share one login on some Macs · c. every Mac has one shared login.

33. **The media Mac's video**
    a. hundreds of GB on the internal disk, stays local *(assumed)* · b. on an external drive · c. small enough to move to the server · d. not sure.

34. **Macs that leave the building**
    a. mine and one or two more *(assumed)* · b. only mine · c. none · d. most of them.

35. **Existing management**
    a. nothing is managed *(assumed)* · b. some Macs are in an MDM · c. at least one is activation-locked to someone who left.

## Files, shares and what goes where

36. **Dashboard from the open internet**
    a. Tailscale only, nothing exposed *(assumed)* · b. a public HTTPS address with a port forward · c. both: public for the portal, Tailscale for admin.

37. **Shares**
    a. staff, leadership, media, kids, graphics *(assumed)* · b. that list plus some (add them) · c. fewer than that · d. one shared folder for everyone.

38. **Proclaim backgrounds, loops, lower thirds**
    a. synced local copy on the media Mac *(assumed)* · b. work straight off the share · c. they stay on the media Mac only.

39. **Share links**
    a. 7 days, everyone can make them *(assumed)* · b. 7 days, admins only · c. longer by default (add how long) · d. no share links at all.

40. **Things that must never be on the server**
    a. giving records stay in the giving system *(assumed)* · b. payroll and counselling notes too · c. nothing is off-limits · d. a list to follow.

41. **Data in a year, excluding video**
    a. under 500 GB · b. under 2 TB *(assumed)* · c. more than 2 TB · d. no idea.

## Remote access and security

42. **Tailscale login**
    a. one shared church login for every device *(assumed)* · b. each person signs in with their own account.

43. **Who may reach the server from home**
    a. staff and media *(assumed)* · b. everyone with an account · c. only me.

44. **Remote desktop from home into**
    a. the media Mac and the lobby PC *(assumed)* · b. the media Mac only · c. nothing · d. a list to follow.

45. **Cyber insurance or a written policy**
    a. no *(assumed)* · b. yes, I will send it · c. not sure.

## The automator, backups and the YouTube side

46. **The automator during the switch-over**
    a. keeps running on the Windows PC until the server's timer is on, then stops *(assumed)* · b. stop it now · c. it is already off.

47. **Backup history**
    a. the default: 14 daily, 8 weekly, 12 monthly *(assumed)* · b. more · c. less.

48. **Off-site copy**
    a. a USB disk I carry *(assumed)* · b. Backblaze B2 (about $6 per TB per month, an estimate) · c. both · d. nowhere yet.

49. **The daily note**
    a. Discord *(assumed)* · b. Slack · c. email · d. none.

## Livestream and media

50. **Streaming setup**
    a. StreamYard in a browser on the media Mac *(assumed)* · b. OBS · c. hardware encoder · d. mixed. Same at Alexandria?

51. **Sunday recordings**
    a. YouTube is the archive; only thumbnails and transcripts live on the server *(assumed)* · b. every recording lands on the Synology too · c. undecided.

## Day to day

52. **A second person for the closet**
    a. nobody yet *(assumed)* · b. one person, name to follow · c. two or more.
