/* V2Ray GeoSiteList wire-format reader. The format is defined in
 * v2ray-core/app/router/routercommon/common.proto. */
#include "geosite.h"
#include "smartdns/dns_conf.h"
#include "smartdns/util.h"

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>

#define GEOSITE_MAX_FILE_SIZE (64 * 1024 * 1024)

struct pb_cursor {
	const unsigned char *pos;
	const unsigned char *end;
};

struct pb_field {
	unsigned int number;
	unsigned int wire_type;
	uint64_t integer;
	struct pb_cursor bytes;
};

static int pb_varint(struct pb_cursor *cursor, uint64_t *value)
{
	uint64_t result = 0;
	for (int i = 0; i < 10 && cursor->pos < cursor->end; i++) {
		unsigned char byte = *cursor->pos++;
		if (i == 9 && byte > 1) return -1;
		result |= (uint64_t)(byte & 0x7f) << (7 * i);
		if (!(byte & 0x80)) {
			*value = result;
			return 0;
		}
	}
	return -1;
}

/* 1: field, 0: end, -1: malformed input. */
static int pb_next(struct pb_cursor *cursor, struct pb_field *field)
{
	uint64_t tag, length;
	if (cursor->pos == cursor->end) return 0;
	if (pb_varint(cursor, &tag) != 0 || (tag >> 3) == 0 || (tag >> 3) > UINT32_MAX) return -1;
	field->number = tag >> 3;
	field->wire_type = tag & 7;
	field->integer = 0;
	field->bytes.pos = field->bytes.end = NULL;
	switch (field->wire_type) {
	case 0:
		return pb_varint(cursor, &field->integer) == 0 ? 1 : -1;
	case 1:
		if (cursor->end - cursor->pos < 8) return -1;
		cursor->pos += 8;
		return 1;
	case 2:
		if (pb_varint(cursor, &length) != 0 || length > (uint64_t)(cursor->end - cursor->pos)) return -1;
		field->bytes.pos = cursor->pos;
		cursor->pos += length;
		field->bytes.end = cursor->pos;
		return 1;
	case 5:
		if (cursor->end - cursor->pos < 4) return -1;
		cursor->pos += 4;
		return 1;
	default:
		return -1;
	}
}

static int pb_equals(struct pb_cursor value, const char *text)
{
	size_t length = value.end - value.pos;
	return strlen(text) == length && strncasecmp((const char *)value.pos, text, length) == 0;
}

static int geosite_attribute_matches(struct pb_cursor attribute, const char *wanted)
{
	struct pb_field field;
	int ret;
	while ((ret = pb_next(&attribute, &field)) > 0) {
		if (field.number == 1 && field.wire_type == 2 && pb_equals(field.bytes, wanted)) return 1;
	}
	return ret < 0 ? -1 : 0;
}

static int geosite_domain(struct pb_cursor cursor, const char *attribute, set_rule_add_func callback, void *priv)
{
	struct pb_field field;
	struct pb_cursor value = {0};
	unsigned int type = 0;
	int matched_attr = attribute == NULL, ret;
	while ((ret = pb_next(&cursor, &field)) > 0) {
		if (field.number == 1 && field.wire_type == 0) {
			type = field.integer;
		} else if (field.number == 2 && field.wire_type == 2) {
			value = field.bytes;
		} else if (field.number == 3 && field.wire_type == 2 && attribute != NULL) {
			int match = geosite_attribute_matches(field.bytes, attribute);
			if (match < 0) return -1;
			matched_attr |= match;
		}
	}
	if (ret < 0 || value.pos == NULL || value.pos == value.end) return -1;
	if (!matched_attr) return 0;
	const char *prefix = type == 0 ? "geosite-keyword:" : type == 1 ? "geosite-regex:" :
		type == 3 ? "-." : type == 2 ? "" : NULL;
	if (prefix == NULL) return -1;
	size_t prefix_len = strlen(prefix);
	size_t length = value.end - value.pos;
	if (memchr(value.pos, 0, length) != NULL ||
		((type == 0 || type == 1) ? length > 4096 : prefix_len + length >= DNS_MAX_CNAME_LEN)) return -1;
	char *domain = malloc(prefix_len + length + 1);
	if (domain == NULL) return -1;
	memcpy(domain, prefix, prefix_len);
	memcpy(domain + prefix_len, value.pos, length);
	domain[prefix_len + length] = 0;
	int result = callback(domain, priv);
	free(domain);
	return result == 0 ? 1 : -1;
}

static int geosite_entry(struct pb_cursor cursor, const char *site, const char *attribute,
				 set_rule_add_func callback, void *priv, int *found, int *matches)
{
	/* The code normally precedes domains, but protobuf does not require order.
	 * Make one pass to find the code, then a second pass to emit domains. */
	struct pb_cursor original = cursor;
	struct pb_field field;
	int ret, matched = 0;
	while ((ret = pb_next(&cursor, &field)) > 0) {
		if (field.number == 1 && field.wire_type == 2 && pb_equals(field.bytes, site)) matched = 1;
	}
	if (ret < 0) return -1;
	if (!matched) return 0;
	*found = 1;
	while ((ret = pb_next(&original, &field)) > 0) {
		if (field.number == 2 && field.wire_type == 2) {
			int emitted = geosite_domain(field.bytes, attribute, callback, priv);
			if (emitted < 0) return -1;
			*matches += emitted;
		}
	}
	return ret < 0 ? -1 : 0;
}

static unsigned char *geosite_read_file(const char *file, size_t *size)
{
	FILE *fp = fopen(file, "rb");
	unsigned char *data = NULL;
	long length;
	if (fp == NULL) return NULL;
	if (fseek(fp, 0, SEEK_END) != 0 || (length = ftell(fp)) <= 0 || length > GEOSITE_MAX_FILE_SIZE ||
		fseek(fp, 0, SEEK_SET) != 0) goto done;
	data = malloc(length);
	if (data == NULL || fread(data, 1, length, fp) != (size_t)length) {
		free(data);
		data = NULL;
		goto done;
	}
	*size = length;
done:
	fclose(fp);
	return data;
}

static int geosite_noop(const char *domain, void *priv)
{
	return 0;
}

static int geosite_validate_rule(const char *domain, void *priv)
{
	if (strncmp(domain, "geosite-regex:", 14) != 0) return 0;
	regex_t regex;
	if (regcomp(&regex, domain + 14, REG_EXTENDED | REG_NOSUB) != 0) return -1;
	regfree(&regex);
	return 0;
}

int geosite_check_site(const char *file, const char *site)
{
	return _config_set_rule_each_from_geosite(file, site, geosite_validate_rule, NULL);
}

int geosite_check_file(const char *file)
{
	size_t size = 0;
	unsigned char *data = geosite_read_file(file, &size);
	if (data == NULL) return -1;
	struct pb_cursor cursor = {data, data + size};
	struct pb_field field;
	int next, entries = 0, ret = -1;
	while ((next = pb_next(&cursor, &field)) > 0) {
		if (field.number != 1 || field.wire_type != 2) continue;
		struct pb_cursor entry = field.bytes;
		struct pb_field item;
		char site[DNS_MAX_CNAME_LEN] = {0};
		int inner;
		while ((inner = pb_next(&entry, &item)) > 0) {
			if (item.number == 1 && item.wire_type == 2) {
				size_t length = item.bytes.end - item.bytes.pos;
				if (length == 0 || length >= sizeof(site)) goto done;
				memcpy(site, item.bytes.pos, length);
				site[length] = 0;
			}
		}
		if (inner < 0 || site[0] == 0) goto done;
		int found = 0, matches = 0;
		if (geosite_entry(field.bytes, site, NULL, geosite_noop, NULL, &found, &matches) != 0 || !found) goto done;
		entries++;
	}
	if (next == 0 && entries > 0) ret = 0;
done:
	free(data);
	return ret;
}

int _config_set_rule_each_from_geosite(const char *file, const char *site, set_rule_add_func callback, void *priv)
{
	unsigned char *data = NULL;
	char category[DNS_MAX_CNAME_LEN];
	const char *attribute = NULL;
	const char *at = strchr(site, '@');
	int ret = -1, found = 0, matches = 0, next;
	size_t size = 0;
	if (at != NULL) {
		if (at == site || at[1] == 0 || (size_t)(at - site) >= sizeof(category)) return -1;
		memcpy(category, site, at - site);
		category[at - site] = 0;
		attribute = at + 1;
	} else {
		if (strlen(site) >= sizeof(category)) return -1;
		strcpy(category, site);
	}
	if (category[0] == 0 || (data = geosite_read_file(file, &size)) == NULL) goto done;
	struct pb_cursor cursor = {data, data + size};
	struct pb_field field;
	while ((next = pb_next(&cursor, &field)) > 0) {
		if (field.number == 1 && field.wire_type == 2 &&
			geosite_entry(field.bytes, category, attribute, callback, priv, &found, &matches) != 0) goto done;
	}
	if (next == 0 && found && matches > 0) ret = 0;
done:
	if (ret != 0) tlog(TLOG_ERROR, "cannot load geosite %s from %s", site, file);
	free(data);
	return ret;
}
