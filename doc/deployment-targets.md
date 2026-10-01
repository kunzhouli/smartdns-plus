# Local deployment targets

| Host | Service | SSH user |
| --- | --- | --- |
| `192.168.100.11` | SmartDNS LXC container | `root` |
| `192.168.100.10` | AdGuard Home LXC container | `root` |

Deploy SmartDNS packages to `192.168.100.11`. The AdGuard Home container is a
separate service and is not a SmartDNS deployment target.

SSH authentication uses a local Ed25519 key. Credentials are not stored in this
repository.

From the configured workstation, connect with `ssh smartdns-lxc` or
`ssh adguard-lxc`. Both aliases use the `root` account and public-key
authentication.
