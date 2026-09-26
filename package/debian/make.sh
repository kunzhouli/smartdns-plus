#!/bin/sh
#
# Copyright (C) 2018-2025 Ruilin Peng (Nick) <pymumu@gmail.com>.
#
# smartdns is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# smartdns is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
CURR_DIR=$(cd $(dirname $0);pwd)
VER="`date +"1.%Y.%m.%d-%H%M"`"
SMARTDNS_DIR=$CURR_DIR/../../
SMARTDNS_CP=$SMARTDNS_DIR/package/copy-smartdns.sh
SMARTDNS_BIN=$SMARTDNS_DIR/src/smartdns
IS_BUILD_SMARTDNS_UI=0

showhelp()
{
	echo "Usage: make [OPTION]"
	echo "Options:"
	echo " -o               output directory."
	echo " --arch           archtecture."
	echo " --ver            version."
	echo " --with-ui        build with smartdns-ui plugin."
	echo " -h               show this message."
}

build()
{
	ROOT=/tmp/smartdns-deiban
	rm -fr $ROOT
	mkdir -p $ROOT
	cd $ROOT/

	cp $CURR_DIR/DEBIAN $ROOT/ -af
	CONTROL=$ROOT/DEBIAN/control
	mkdir $ROOT/usr/sbin -p
	mkdir $ROOT/etc/smartdns/ -p
	mkdir $ROOT/etc/default/ -p
	mkdir $ROOT/lib/systemd/system/ -p


	pkgver=$(echo ${VER}| sed 's/^1\.//g')
	sed -i "s/Version:.*/Version: ${pkgver}/" $ROOT/DEBIAN/control
	sed -i "s/Architecture:.*/Architecture: $ARCH/" $ROOT/DEBIAN/control
	chmod 0755 $ROOT/DEBIAN/prerm
	chmod 0755 $ROOT/DEBIAN/postinst

	cp $SMARTDNS_DIR/etc/smartdns/smartdns.conf  $ROOT/etc/smartdns/
	cp $SMARTDNS_DIR/etc/default/smartdns  $ROOT/etc/default/
	cp $SMARTDNS_DIR/systemd/smartdns.service $ROOT/lib/systemd/system/ 
	mkdir -p $ROOT/usr/lib/smartdns
	cp $CURR_DIR/geosite-manager.py $ROOT/usr/lib/smartdns/
	cp $CURR_DIR/geosite-scheduled $ROOT/usr/lib/smartdns/
	chmod 0755 $ROOT/usr/lib/smartdns/geosite-manager.py $ROOT/usr/lib/smartdns/geosite-scheduled
	cp $CURR_DIR/geosite-update.service $ROOT/lib/systemd/system/smartdns-geosite-update.service
	cp $CURR_DIR/geosite-update.timer $ROOT/lib/systemd/system/smartdns-geosite-update.timer
	cp $CURR_DIR/cloudflare-manager.py $ROOT/usr/lib/smartdns/
	cp $CURR_DIR/cloudflare-scheduled $ROOT/usr/lib/smartdns/
	chmod 0755 $ROOT/usr/lib/smartdns/cloudflare-manager.py $ROOT/usr/lib/smartdns/cloudflare-scheduled
	cp $CURR_DIR/cloudflare-speedtest.service $ROOT/lib/systemd/system/smartdns-cloudflare-speedtest.service
	cp $CURR_DIR/cloudflare-speedtest.timer $ROOT/lib/systemd/system/smartdns-cloudflare-speedtest.timer
	case "$ARCH" in
		amd64) CFST_ARCH=amd64; CFST_SHA=c4c8fc76b4e1bf2bdb5ced8b765956d82dda7bc4eb59df5c04053f0f7db98d90 ;;
		arm64) CFST_ARCH=arm64; CFST_SHA=0ac992fcf24d4684caed33620deb9b83ce82f32d2418dc1f90be490ce5900300 ;;
		armhf) CFST_ARCH=armv7; CFST_SHA=73386234fe07a766071709859168e19b37f6878345317ccaa992efe35f4ef5f0 ;;
		*) echo "Unsupported CloudflareSpeedTest Debian architecture: $ARCH"; return 1 ;;
	esac
	CFST_ARCHIVE="$WORKDIR/cfst-v2.3.5-linux-$CFST_ARCH.tar.gz"
	if [ ! -s "$CFST_ARCHIVE" ]; then
		CFST_URL="https://github.com/XIU2/CloudflareSpeedTest/releases/download/v2.3.5/cfst_linux_$CFST_ARCH.tar.gz"
		if [ -n "$SMARTDNS_GITHUB_PROXY" ]; then
			CFST_URL="${SMARTDNS_GITHUB_PROXY%/}/$CFST_URL"
		fi
		wget -q -O "$CFST_ARCHIVE" "$CFST_URL" || return 1
	fi
	printf '%s  %s\n' "$CFST_SHA" "$CFST_ARCHIVE" | sha256sum -c - || return 1
	tar -xOzf "$CFST_ARCHIVE" "cfst_linux_$CFST_ARCH/cfst" > "$ROOT/usr/lib/smartdns/cfst" || return 1
	chmod 0755 "$ROOT/usr/lib/smartdns/cfst"
	mkdir -p "$ROOT/usr/share/doc/smartdns"
	cp /usr/share/common-licenses/GPL-3 "$ROOT/usr/share/doc/smartdns/CloudflareSpeedTest.LICENSE" || return 1
	cp "$CURR_DIR/CloudflareSpeedTest.NOTICE" "$ROOT/usr/share/doc/smartdns/" || return 1
	cp "$CURR_DIR/DEBIAN/copyright" "$ROOT/usr/share/doc/smartdns/copyright" || return 1

	if [ $IS_BUILD_SMARTDNS_UI -eq 1 ]; then
		mkdir $ROOT/usr/local/lib/smartdns -p
		mkdir $ROOT/usr/share/smartdns/wwwroot -p
		cp $SMARTDNS_DIR/plugin/smartdns-ui/target/smartdns_ui.so $ROOT/usr/local/lib/smartdns/smartdns_ui.so -a
		if [ $? -ne 0 ]; then
			echo "Failed to copy smartdns-ui plugin."
			return 1
		fi

		cp $WORKDIR/smartdns-webui/out/* $ROOT/usr/share/smartdns/wwwroot/ -a
		if [ $? -ne 0 ]; then
			echo "Failed to copy smartdns-ui plugin."
			return 1
		fi
		cat >> $ROOT/etc/smartdns/smartdns.conf <<'EOF'

# Debian Web UI
plugin /usr/local/lib/smartdns/smartdns_ui.so
smartdns-ui.www-root /usr/share/smartdns/wwwroot
smartdns-ui.ip http://127.0.0.1:6080
EOF
	else
		echo "smartdns-ui plugin not found, skipping copy."
	fi
	printf '\n# Debian GeoSite and Cloudflare rules (managed by Web UI)\nconf-file /etc/smartdns/geosite.conf\nconf-file /etc/smartdns/cloudflare.conf\n' >> $ROOT/etc/smartdns/smartdns.conf

	$SMARTDNS_CP $ROOT
	if [ $? -ne 0 ]; then
		echo "copy smartdns file failed."
		return 1
	fi
	chmod +x $ROOT/usr/sbin/smartdns 2>/dev/null

	dpkg-deb --root-owner-group -b $ROOT $OUTPUTDIR/smartdns.$VER.$FILEARCH.deb || return 1

	rm -fr $ROOT/
}

main()
{
	OPTS=`getopt -o o:h --long arch:,ver:,with-ui,filearch: \
		-n  "" -- "$@"`

	if [ $? != 0 ] ; then echo "Terminating..." >&2 ; exit 1 ; fi

	# Note the quotes around `$TEMP': they are essential!
	eval set -- "$OPTS"

	while true; do
		case "$1" in
		--arch)
			ARCH="$2"
			shift 2;;
		--filearch)
			FILEARCH="$2"
			shift 2;;
		--with-ui)
			IS_BUILD_SMARTDNS_UI=1
			shift ;;
		--ver)
			VER="$2"
			shift 2;;
		-o )
			OUTPUTDIR="$2"
			shift 2;;
		-h | --help )
			showhelp
			return 0
			shift ;;
		-- ) shift; break ;;
		* ) break ;;
		esac
	done

	if [ -z "$ARCH" ]; then
		echo "please input arch."
		return 1;
	fi

	if [ -z "$FILEARCH" ]; then
		FILEARCH=$ARCH
	fi

	if [ -z "$OUTPUTDIR" ]; then
		OUTPUTDIR=$CURR_DIR;
	fi

	build
}

main $@
exit $?
