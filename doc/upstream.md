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
**Exclude from default group** makes the server available only to its assigned
groups. GeoSite route rules can use those group names.

The Web UI stores its entries in `/etc/smartdns/upstream.json` and generates
`/etc/smartdns/upstream.conf`. It does not rewrite servers entered manually in
`smartdns.conf`; those remain visible in the runtime status table and are listed
as read-only in the management panel. A group referenced by a GeoSite route
cannot be deleted until that route is changed.
