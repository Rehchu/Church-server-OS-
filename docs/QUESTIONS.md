# Questions for Bradly

Fifty-two questions, grouped. Each one has a line on why it matters and what
I assume until it is answered. The ones marked **before the wipe** change
what the installer does on day 1 (docs/SETUP-GUIDE.md § 3); the rest can
wait until that part of the plan comes up. Answer in any order, in any
form; a photo of a router page counts.

---

## The OptiPlex and the Synology

1. **Which OptiPlex is it: the model number on the sticker (for example "OptiPlex 7050 SFF"), and how much RAM?** *before the wipe*
   Decides whether it can run the domain, Docker apps and Guacamole at once. I assume 8 GB or more and a 4-core i5 or better; under 8 GB I drop Guacamole and Vaultwarden from the day-1 plan.

2. **What drives are in it: how many, what size, SSD or spinning?** *before the wipe*
   Decides whether home folders live on the server or on the Synology, and whether the OS gets its own disk. I assume one SSD of 256 GB or more; with a single small disk the homes go on the Synology.

3. **Does it have a second drive bay or an M.2 slot you could add a drive to?**
   A second SSD for `/srv/arise` keeps the OS and the data apart; cheap insurance. I assume no until you look.

4. **Which Synology model, how many bays are filled, what size, and what RAID (SHR, SHR-2, RAID 5)?** *before the wipe*
   Decides how much backup history fits and whether one drive can fail without data loss. I assume four bays, SHR, around 10 TB usable.

5. **What is already on the Synology, and does any of it need to stay where it is?**
   The installer makes `arise-backups/` and `homes/` shares on it; I do not touch existing shares. I assume there is existing data and it stays.

6. **Does the Synology have a static address and a DSM admin account you know the password for?** *before the wipe*
   `arisectl nas mount` needs both. I assume yes.

7. **When the server moves to the Hub, does the Synology move with it?**
   docs/MOVING-DAY.md assumes yes (it is the backup target and should sit next to the server). If it stays at Pineville, backups cross the VPN nightly and home folders are slow for the Hub.

8. **Is there a UPS at Pineville now, and will there be one at the Hub?**
   A domain controller that loses power mid-write can corrupt its database. I assume no UPS yet; docs/IDEAS.md has the recommendation.

9. **Will the closet stay cool, and is there a way to get a network cable to it?**
   An OptiPlex in a hot closet throttles and dies early. I assume a wired port exists.

## The Pineville network and the Cisco

10. **The exact Cisco model (the sticker, or the login page title): Catalyst, Cisco Business, Small Business SG, Meraki?** *before the wipe*
    Decides whether the switch routes between VLANs itself or the router does, and whether VLANs exist at all. I assume a layer-2 Cisco Business switch with VLANs set up by whoever installed it.

11. **Who set the switch up, and do you have its admin login?**
    Without the login, the VLAN plan in docs/NETWORK.md stays a plan. I assume you have it or can get it.

12. **What networks exist today: a list of Wi-Fi names and what plugs into which, and the subnet of each (`192.168.1.x`, `10.0.0.x`)?** *before the wipe*
    The server needs one subnet to live on and the VPN needs no two sites to share one. I assume one flat `192.168.1.0/24` plus a guest Wi-Fi.

13. **What is the router, and is it also the ISP's modem?**
    Decides where DHCP, DNS and the firewall rules live, and whether it can hold a static route. I assume an ISP box that cannot do VLANs or static routes.

14. **What device hands out addresses (DHCP): the router, the Cisco, something else?**
    The one DNS setting that makes the domain work is on that device. I assume the router.

15. **The Pineville internet: who is the ISP, and what are the download and upload speeds?**
    Upload is shared between the livestream and every sync out of the building. I assume 20 Mbit/s up or less until measured.

16. **Is the public address static, and can you forward a port if you ever need to?**
    Tailscale needs neither; WireGuard or a public dashboard door needs both. I assume dynamic and forwarding allowed.

17. **Which Wi-Fi do guests use on Sunday, and is it separate from the staff network?**
    If guests can reach the server, that is the first thing to fix. I assume there is a "guest" network but it is not a separate VLAN.

18. **Are the cameras, the thermostat and any door locks on the same network as the office Macs?**
    They should not be able to reach the server. I assume they are all on the one network.

## Alexandria

19. **What is at Alexandria today: how many Macs, PCs, iPads, a printer, a check-in station?**
    Decides whether every device runs Tailscale (a few laptops) or the site gets a route box (anything you cannot install an app on). I assume two or three Macs and a printer.

20. **What is the Alexandria router and ISP, and the upload speed there?**
    Same reasons as 13 and 15. I assume an ISP box.

21. **Is there somewhere at Alexandria for a small always-on box (a Raspberry Pi or mini PC) next to the router, on a UPS?**
    That box is how the whole site joins the church network. I assume yes.

22. **Does anyone at Alexandria run a livestream from there?**
    If so the same bandwidth rule applies: the stream never goes through the VPN. I assume Alexandria streams occasionally.

## People and accounts

23. **What username rule do you want: `jsmith`, or first names (`vanessa`), or something else?**
    The Mac's existing local account names should match the directory names for the enrol script to pair them. I assume first initial plus surname, and first name where the church already uses it (`bradly`).

24. **The list of people who get accounts, with their role from the table in docs/SETUP-GUIDE.md § 2 (admin, staff, leadership, media, volunteer).**
    I will not invent names. The pastors in your notes get accounts when you say which ones, in what group.

25. **Does anyone besides you get admin? If so, who, and do they get SSH too?**
    `Domain Admins` is the group; SSH keys are per person. I assume only you.

26. **Should a person's password expire, and how often?**
    docs/DIRECTORY.md § Password policy has the default: 12 characters minimum, no expiry, lockout after 10 failures. I assume that stays.

27. **Do volunteers get a home folder on the server, or only a login for the check-in and lobby machines?**
    Home folders cost disk and backup space per person. I assume every account gets a home.

28. **The kids check-in station: what software, what hardware, who logs into it?**
    Decides whether it joins the domain with a shared account or stays as it is on its own VLAN. I assume a Windows PC with a shared `checkin` login.

29. **Is there a shared church Google account (for Tailscale, for the daily-note webhook, for the YouTube token), and who else knows its password?**
    One church login on the free Tailscale plan is the cheapest setup; it should not be a personal account. I assume one exists; I will not guess its address.

## Macs and PCs

30. **How many Macs in total across the three sites, roughly what age, and what macOS version is on each?**
    Binding works on every current macOS; the oldest one sets the floor. I assume six to ten Macs on macOS 12 or newer.

31. **How many Windows PCs, and are any of them Windows Home (which cannot join a domain)?**
    Home edition cannot join; Pro can. I assume Pro on the office PCs and unknown on the lobby PC.

32. **On the Macs that already have local users: how many users per Mac, and do any two people share one login?**
    The enrol script makes one directory user per local user. A shared login becomes one shared directory user. I assume one person per login, except the media Mac.

33. **The media Mac: how big is the video folder, and where does it live now (the internal disk, an external drive)?**
    It must not be synced to the server by the home-sync agent. I assume hundreds of gigabytes on the internal disk, and it stays local.

34. **Do any Macs leave the building (laptops that go home, to Alexandria, to conferences)?**
    Those get Tailscale and mobile accounts; desk Macs need only the LAN. I assume yours and one or two others.

35. **Is anyone's Mac managed by something already (an MDM, Apple Business Manager, Find My locked to someone who left)?**
    An activation-locked Mac cannot be re-enrolled. I assume nothing is managed.

## Files, shares and what goes where

36. **Do you want the dashboard reachable from the open internet (a public `https://files.arisecenla.church` with a port forward), or only over Tailscale?**
    docs/SETUP-GUIDE.md § 9. Tailscale-only is free and exposes nothing; a public door means a member can sign in from any browser. I assume Tailscale-only until you say otherwise.

37. **Which shares exist in your head today: `staff`, `leadership`, `media`, `kids`, `graphics` are my guess. What is missing, what is wrong?**
    Each share is a folder with groups on it. I assume those five.

38. **Where do the Proclaim backgrounds, loops and lower thirds live now, and should the media Mac keep a local copy that syncs (Syncthing) or work straight off the share?**
    Straight off the share over Wi-Fi is slow for loops. I assume a synced local copy on the media Mac.

39. **How long should a share link live by default, and should members be allowed to make them at all, or only admins?**
    I assume 7 days and everyone, revocable by the person and by you.

40. **Is there anything that must never be on the server (payroll, counselling notes, giving records)?**
    Those go in a share with only `Leadership` on it, or stay off the box entirely. I assume giving records stay in whatever system handles giving now.

41. **How much total data do you expect in home folders and shares in a year?**
    Decides disk and backup retention. I assume under 2 TB excluding video.

## Remote access and security

42. **Tailscale: one shared church login for every device, or each person signs in with their own account?**
    The free plan is one user; a second login is where the plan question starts. I assume one church login.

43. **Who should be able to reach the server from home at all: everyone with an account, staff only, or only you?**
    Decides who gets the Tailscale app and the dashboard address. I assume staff and media get the portal; volunteers do not.

44. **Remote desktop: which computers do you need to reach from home (the media Mac, the lobby PC, the check-in station)?**
    Each is a Guacamole connection and needs sleep turned off. I assume the media Mac and the lobby PC.

45. **Does the church have cyber insurance, or any policy that says how passwords and backups must be handled?**
    It would set the password policy and the off-site copy rule. I assume no.

## The automator, backups and the YouTube side

46. **Does the automator keep running on the Windows PC until the server is up, or is it off during the switch-over?**
    Two copies running at 02:05 would both write to YouTube. I assume the Windows copy is stopped the day the server's timer is enabled, and not before.

47. **How many nights of backup history do you want to be able to go back: the default is 14 daily, 8 weekly, 12 monthly.**
    More history, more Synology space. I assume the default.

48. **Where should the off-site copy of the backups go: a USB disk you carry, Backblaze B2 (around $6 per TB per month, an estimate), or nowhere yet?**
    A fire at Pineville takes the server and the Synology together. I assume a USB disk until you choose.

49. **Discord or Slack for the daily note, and which channel?**
    The webhook URL goes in `arise.toml` `[notify]`. I assume Discord.

## Livestream and media

50. **The streaming setup: StreamYard in a browser on the media Mac, or OBS, or hardware? Same at Alexandria?**
    Decides which machine must never have a full-tunnel VPN profile. I assume StreamYard on the media Mac at Pineville.

51. **Do the Sunday recordings need to end up on the server at all, or is YouTube the archive?**
    A 6 GB file per service adds up fast on the Synology. I assume YouTube is the archive and only thumbnails, transcripts and the automator's files live on the server.

## Day to day and who else helps

52. **Who is the second person who can get into the closet, restart the box and read this repo if you are away?**
    One person is a single point of failure. I assume nobody yet; the answer decides whether the printed checklists and a second admin account exist.
