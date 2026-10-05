# Cloudflare IP acceleration on Debian

SmartDNS can replace an A or AAAA answer when the original address belongs to
Cloudflare's published IP ranges. The replacement is the fastest address of the
same family selected by CloudflareSpeedTest. Other answers are unaffected.
SmartDNS applies this with its existing `ip-alias` rules, so an actual DNS
answer IP must match a Cloudflare range before a replacement is made.

The Debian package with Web UI includes CloudflareSpeedTest v2.3.5. In
**Cloudflare IP Optimization**, click **Run speed test now** to run manually and
watch the live log. Enable acceleration and save to apply selected IPs to DNS
answers. Scheduled runs are disabled by default;
enable them separately to choose a server-local run time and repeat interval in
days. The timer checks the chosen time each minute when enabled; a failed test
keeps the previous working IPs and rules. IPv4 and IPv6
are measured separately. If IPv6 is unavailable, IPv4 can still update.

The feature starts disabled and makes no answer changes until a test finds a
working IP with a positive download speed. CloudflareSpeedTest uses its built-in
download URL. The Web UI shows both selected IPs, the last attempt, the last
successful run, and errors.

Settings are stored in `/etc/smartdns/cloudflare.json`, the selected IPs and
ranges in `/etc/smartdns/cloudflare-state.json`, and generated rules in
`/etc/smartdns/cloudflare.conf`. To test manually from a shell:

```sh
sudo /usr/lib/smartdns/cloudflare-manager.py run
sudo systemctl restart smartdns
```

The package downloads a pinned CloudflareSpeedTest binary at build time. Set
`SMARTDNS_GITHUB_PROXY=https://your-proxy/` during the Debian package build if
GitHub release downloads need a proxy.

Data sources: [CloudflareSpeedTest](https://github.com/XIU2/CloudflareSpeedTest)
and [Cloudflare's official IP ranges API](https://developers.cloudflare.com/api/resources/ips/).
