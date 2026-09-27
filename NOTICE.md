# SmartDNS Plus: copyright and upstream projects

Copyright © 2026 Kaiden for the SmartDNS Plus modifications. The original
authors' copyright notices remain in their source files and license texts.

This derivative uses or builds on:

- [SmartDNS](https://github.com/pymumu/smartdns) by Ruilin Peng (Nick), licensed under GPL-3.0-or-later. It supplies the DNS server and plugin framework.
- [smartdns-webui](https://github.com/pymumu/smartdns-webui) by Ruilin Peng (Nick), licensed under MIT. It supplies the Web UI that this project extends.
- [CloudflareSpeedTest](https://github.com/XIU2/CloudflareSpeedTest) by XIU2 and contributors, licensed under GPL-3.0. Its unmodified `cfst` binary is bundled in the Debian package.

GeoSite's default runtime data source is
[v2fly/domain-list-community](https://github.com/v2fly/domain-list-community).
The Cloudflare acceleration feature was informed by the approach used in
[mosdns](https://github.com/IrineSistiana/mosdns); no mosdns code is bundled.

The Debian package includes the GPL-3.0 and upstream Web UI MIT license texts,
CloudflareSpeedTest attribution, and this notice under
`/usr/share/doc/smartdns/`.
