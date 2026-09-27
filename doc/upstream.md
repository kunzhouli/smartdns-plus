# Debian Web UI: upstream DNS servers and server groups

The **Upstream Servers** page now has a management panel above the live status
table. Add a DNS endpoint, create groups, assign one or more groups to each
server, and save. SmartDNS restarts to load the new configuration.

Endpoints accept SmartDNS `server` syntax, for example:

- `1.1.1.1` for UDP DNS
- `tcp://1.1.1.1:53` for TCP DNS
- `tls://dns.google:853` for DNS over TLS
- `https://dns.google/dns-query` for DNS over HTTPS

For a hostname-based endpoint, **Host IP** can provide its bootstrap address.
Choose a **Default DNS group** to route queries without a matching rule through
that group's enabled servers. Servers assigned only to other groups are excluded
from the SmartDNS default group. For example, choose `Overseas` to keep `China`
upstreams available to explicit GeoSite rules without using them for unmatched
queries. The legacy per-server **Exclude from default group** switches are shown
only when no default DNS group is selected. GeoSite route rules can use the same
group names.

The Web UI stores its entries in `/etc/smartdns/upstream.json` and generates
`/etc/smartdns/upstream.conf`. It does not rewrite servers entered manually in
`smartdns.conf`; those remain visible in the runtime status table and are listed
as read-only in the management panel. Manual servers may still be in the default
group; exclude them in `smartdns.conf` if necessary. A group referenced by a GeoSite route
cannot be deleted until that route is changed.
