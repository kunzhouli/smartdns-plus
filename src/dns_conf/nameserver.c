/*************************************************************************
 *
 * Copyright (C) 2018-2025 Ruilin Peng (Nick) <pymumu@gmail.com>.
 *
 * smartdns is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * smartdns is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program.  If not, see <http://www.gnu.org/licenses/>.
 */

#include "nameserver.h"
#include "domain_rule.h"
#include "get_domain.h"
#include "server_group.h"
#include <strings.h>

int _config_priority_nameserver(void *data, int argc, char *argv[])
{
	struct dns_priority_nameserver_rule *rule;
	const char *pattern;
	size_t len;
	(void)data;
	if (argc != 3 || argv[1][0] != '/' || (len = strlen(argv[1])) < 3 || argv[1][len - 1] != '/' ||
		argv[2][0] == '\0' || strlen(argv[2]) >= DNS_GROUP_NAME_LEN ||
		strspn(argv[2], "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_.-") != strlen(argv[2])) {
		return -1;
	}
	rule = calloc(1, sizeof(*rule));
	if (rule == NULL) {
		return -1;
	}
	rule->pattern = strndup(argv[1] + 1, len - 2);
	if (rule->pattern == NULL) {
		free(rule);
		return -1;
	}
	pattern = rule->pattern;
	if (strncmp(pattern, "regex:", 6) == 0) {
		rule->match_type = 3;
		pattern += 6;
	} else if (strncmp(pattern, "*.", 2) == 0) {
		rule->match_type = 1;
		pattern += 2;
	} else if (strncmp(pattern, "-.", 2) == 0) {
		rule->match_type = 2;
		pattern += 2;
	}
	if (*pattern == '\0' || strchr(pattern, '/') != NULL) {
		free(rule->pattern);
		free(rule);
		return -1;
	}
	if (rule->match_type == 3 && regcomp(&rule->regex, pattern, REG_EXTENDED | REG_NOSUB | REG_ICASE) != 0) {
		free(rule->pattern);
		free(rule);
		return -1;
	}
	if (pattern != rule->pattern) {
		memmove(rule->pattern, pattern, strlen(pattern) + 1);
	}
	rule->nameserver.group_name = _dns_conf_get_group_name(argv[2]);
	if (rule->nameserver.group_name == NULL) {
		if (rule->match_type == 3) {
			regfree(&rule->regex);
		}
		free(rule->pattern);
		free(rule);
		return -1;
	}
	list_add_tail(&rule->list, &dns_conf.priority_nameservers);
	return 0;
}

const struct dns_nameserver_rule *_config_priority_nameserver_match(const char *domain)
{
	struct dns_priority_nameserver_rule *rule;
	size_t domain_len = strlen(domain);
	list_for_each_entry(rule, &dns_conf.priority_nameservers, list)
	{
		size_t pattern_len = strlen(rule->pattern);
		if (rule->match_type == 3) {
			if (regexec(&rule->regex, domain, 0, NULL, 0) == 0) {
				return &rule->nameserver;
			}
			continue;
		}
		if (domain_len < pattern_len || strcasecmp(domain + domain_len - pattern_len, rule->pattern) != 0) {
			continue;
		}
		if (domain_len == pattern_len && rule->match_type != 1) {
			return &rule->nameserver;
		}
		if (domain_len > pattern_len && domain[domain_len - pattern_len - 1] == '.' && rule->match_type != 2) {
			return &rule->nameserver;
		}
	}
	return NULL;
}

void _config_priority_nameserver_destroy(void)
{
	struct dns_priority_nameserver_rule *rule, *next;
	list_for_each_entry_safe(rule, next, &dns_conf.priority_nameservers, list)
	{
		list_del(&rule->list);
		if (rule->match_type == 3) {
			regfree(&rule->regex);
		}
		free(rule->pattern);
		free(rule);
	}
}

int _conf_domain_rule_nameserver(const char *domain, const char *group_name)
{
	struct dns_nameserver_rule *nameserver_rule = NULL;
	const char *group = NULL;

	if (strncmp(group_name, "-", sizeof("-")) != 0) {
		group = _dns_conf_get_group_name(group_name);
		if (group == NULL) {
			goto errout;
		}

		nameserver_rule = _new_dns_rule(DOMAIN_RULE_NAMESERVER);
		if (nameserver_rule == NULL) {
			goto errout;
		}

		nameserver_rule->group_name = group;
	} else {
		/* ignore this domain */
		if (_config_domain_rule_flag_set(domain, DOMAIN_FLAG_NAMESERVER_IGNORE, 0) != 0) {
			goto errout;
		}

		return 0;
	}

	if (_config_domain_rule_add(domain, DOMAIN_RULE_NAMESERVER, nameserver_rule) != 0) {
		goto errout;
	}

	_dns_rule_put(&nameserver_rule->head);

	return 0;
errout:
	if (nameserver_rule) {
		_dns_rule_put(&nameserver_rule->head);
	}

	tlog(TLOG_ERROR, "add nameserver %s, %s failed", domain, group_name);
	return 0;
}

int _config_nameserver(void *data, int argc, char *argv[])
{
	char domain[DNS_MAX_CONF_CNAME_LEN];
	char *value = argv[1];

	if (argc <= 1) {
		goto errout;
	}

	if (_get_domain(value, domain, DNS_MAX_CONF_CNAME_LEN, &value) != 0) {
		goto errout;
	}

	return _conf_domain_rule_nameserver(domain, value);
errout:
	tlog(TLOG_ERROR, "add nameserver %s failed", value);
	return 0;
}
