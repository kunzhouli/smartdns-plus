# Domain routing rules on Debian

Open **Rules → Domain rules** in the Web UI to send a domain to a DNS server
group. Create the group and assign upstream DNS servers under **Upstream
Servers** first. The group field also accepts a group already defined in a
hand-written SmartDNS configuration file.

For example, `example.com` matches that domain and its subdomains.
`*.example.com` matches subdomains only; `-.example.com` matches the exact
domain only. Domain routing rules are written to
`/etc/smartdns/domain-routes.json` and rendered as SmartDNS `domain-rules`
entries in `/etc/smartdns/domain-routes.conf`.

**Rules → GeoSite rules** contains the existing GeoSite source, automatic
updates, and category routing settings. Both rule types are stored separately
from hand-written SmartDNS configuration. Removing a Web UI managed DNS group
that is still referenced by either rule type is rejected.
