# Debian Web UI: upstream DNS servers and server groups

The **Upstream Servers** page now has a management panel above the live status
table. Add a DNS endpoint, create groups, assign one or more groups to each
server, and save. SmartDNS restarts to load the new configuration.

Each group lists its enabled servers in query order. Move servers up or down
within that group, then enable **Query in order until an IP is found** to use
the order for A and AAAA lookups. Set **Servers queried in parallel** to `1`
for one server at a time, or a larger number to send each batch concurrently.
The next batch is sent when the current batch returns without an IP or times
out. Other DNS query types keep their existing behavior. Groups with ordered
queries disabled also keep the existing fanout behavior. A selected default
DNS group uses the same order and parallel count for unmatched queries.

Endpoints accept SmartDNS `server` syntax, for example:

- `1.1.1.1` for UDP DNS
- `tcp://1.1.1.1:53` for TCP DNS
- `tls://dns.google:853` for DNS over TLS
- `https://dns.google/dns-query` for DNS over HTTPS

Each server group can have an optional **Bootstrap DNS** address, such as
`1.1.1.1` or `1.1.1.1:53`. This is an ordinary UDP DNS server used to resolve
the hostnames of that group's DoH, DoT, or other hostname-based upstreams.
Bootstrap servers are excluded from normal client queries. If the same upstream
hostname appears in multiple groups, those groups must use the same bootstrap
DNS setting, because SmartDNS resolves an upstream hostname globally.
Groups without a bootstrap DNS continue using the existing upstream hostname
resolution behavior.

For an individual hostname-based endpoint, **Host IP** can still pin its
connection to a specific IP without a DNS lookup.
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
