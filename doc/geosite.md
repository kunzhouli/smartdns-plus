# Geosite rules

SmartDNS reads the V2Ray `geosite.dat`/`dlc.dat` GeoSiteList format. A set
selects one category, optionally filtered by an attribute. Root domains match
the domain and its subdomains; full domains match exactly. Keyword and regular
expression entries are also matched. Regular expressions use POSIX extended
syntax, so expressions using Go-specific syntax may be rejected during loading.

```conf
domain-set -name non-cn -type geosite -site geolocation-!cn -file /etc/smartdns/geosite.dat
domain-rules /domain-set:non-cn/ -nameserver overseas

domain-set -name cn-ads -type geosite -site category-ads-all@ads -file /etc/smartdns/geosite.dat
domain-rules /domain-set:cn-ads/ -address #
```

## Debian with Web UI

Build the Debian package with the Web UI enabled:

```sh
PATH="$HOME/.cargo/bin:$PATH" ./package/build-pkg.sh --platform debian --arch amd64 --with-ui
deb=$(ls -t ./package/smartdns.*.amd64.deb | head -n 1)
sudo apt install "$deb"
```

The package installs the Web UI plugin, a GeoSite manager, and a systemd timer.
Open `http://127.0.0.1:6080` locally (or expose it through your own reverse
proxy), sign in with the upstream default `admin` / `password`, and change the
password in **Settings → Password**. Then use **Settings → GeoSite** to set the
source URL, optional GitHub proxy prefix, automatic update interval, and
category rules. A route rule needs an existing SmartDNS nameserver group; a
block rule returns an empty address.
Use **Update GeoSite now** to fetch and validate the data immediately.

The manager keeps settings in `/etc/smartdns/geosite.json`, data in
`/etc/smartdns/geosite.dat`, and generated rules in
`/etc/smartdns/geosite.conf`. The systemd timer checks hourly and downloads
only when the configured interval has elapsed. A failed download or validation
keeps the previous data and rules. The source and proxy can also be edited in
`geosite.json` if the Web UI is unavailable; run
`sudo /usr/lib/smartdns/geosite-manager.py update` and
`sudo systemctl restart smartdns` afterward.

The default data source is
`https://github.com/v2fly/domain-list-community/releases/latest/download/dlc.dat`.
The GitHub proxy setting is a URL prefix: if it is `https://proxy.example/`,
the default source is requested through
`https://proxy.example/https://github.com/v2fly/domain-list-community/releases/latest/download/dlc.dat`.
