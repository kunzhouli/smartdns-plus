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
The run log omits the animated per-IP progress frames and retains status and
diagnostic lines. **Stop speed test** terminates the active local or remote
worker and keeps the previous selected IPs and rules. **Clear log** removes
the visible run history; a test that is still running may append new lines.

The feature starts disabled and makes no answer changes until a test finds a
working IP with a positive download speed. CloudflareSpeedTest uses Cloudflare's
speed test URL and continues past candidates with zero download speed. The Web UI
shows both selected IPs, the last attempt, the last successful run, and errors.

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

## Run the speed test from a direct-connect LXC

When SmartDNS itself must use a Passwall proxy, run only CloudflareSpeedTest on a
second LXC with a different LAN IP. Set that helper IP to **direct** in Passwall
access control. Keep the SmartDNS LXC on its existing proxy rule. Do not add
Cloudflare ranges to Passwall's global direct-IP list: websites such as x.com
may share those ranges and still need the proxy.

Install `/usr/lib/smartdns/cfst` and `/usr/lib/smartdns/cloudflare-cfst-remote`
from the Debian package on the helper LXC. Give the helper a dedicated SSH user
with access to both executable files. On the SmartDNS LXC, create an SSH key
readable by the SmartDNS service, authorize its public key for that user, and
pin the helper's verified SSH host key in
`/etc/smartdns/cfst-known-hosts`. Do not store a password in Cloudflare settings.
Install `openssh-client` on the SmartDNS LXC if `ssh` is not already present.
The helper must have a default gateway; configure it on the LXC's virtual NIC
in Proxmox so the route survives a restart.
The helper's `authorized_keys` entry can use
`restrict,command="/usr/lib/smartdns/cloudflare-cfst-remote"` before the public
key to allow only the speed-test command. The script accepts only a validated
thread count and a bounded IP list over SSH standard input.

In **Cloudflare IP Optimization**, choose **Direct-connect SSH helper**, enter
the helper's address, SSH user, port, and private key path, then save. The
regular **Run speed test now** button and schedule use the helper. The
Cloudflare IP-range API request, selected-IP validation, state, live log, and
generated `cloudflare.conf` remain on the SmartDNS LXC. The helper receives
only the candidate ranges and thread count and returns a CSV result. Both
LXC containers need a working network route to each other; only the helper's
external traffic should bypass Passwall.

Data sources: [CloudflareSpeedTest](https://github.com/XIU2/CloudflareSpeedTest)
and [Cloudflare's official IP ranges API](https://developers.cloudflare.com/api/resources/ips/).
