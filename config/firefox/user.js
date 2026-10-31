// ariseOS kiosk profile. Most settings are enforced by the enterprise policy
// (/etc/firefox/policies/policies.json); these are profile-only niceties.
user_pref("browser.startup.homepage_override.mstone", "ignore");
user_pref("browser.shell.checkDefaultBrowser", false);
user_pref("browser.tabs.warnOnClose", false);
user_pref("browser.tabs.warnOnCloseOtherTabs", false);
user_pref("browser.warnOnQuitShortcut", false);
user_pref("browser.download.panel.shown", true);
user_pref("browser.compactmode.show", true);
user_pref("font.name.sans-serif.x-western", "Oswald");
user_pref("browser.display.background_color.dark", "#0A0A0C");
