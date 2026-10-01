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

#include "server_group.h"
#include "smartdns/lib/stringutil.h"
#include "smartdns/util.h"

/* dns groups */
struct dns_group_table dns_group_table;

int _config_server_group_parallel(void *data, int argc, char *argv[])
{
	struct dns_server_groups *group = NULL;
	char *end = NULL;
	long parallel = 0;
	if (argc != 3) {
		return -1;
	}
	parallel = strtol(argv[2], &end, 10);
	if (*argv[2] == '\0' || *end != '\0' || parallel < 1 || parallel > 100) {
		return -1;
	}
	group = _dns_conf_get_group(argv[1]);
	if (!group) {
		return -1;
	}
	group->ordered_parallel = (int)parallel;
	return 0;
}

struct dns_server_groups *_dns_conf_get_group(const char *group_name)
{
	uint32_t key = 0;
	struct dns_server_groups *group = NULL;

	key = hash_string(group_name);
	hash_for_each_possible(dns_group_table.group, group, node, key)
	{
		if (strncmp(group->group_name, group_name, DNS_GROUP_NAME_LEN) == 0) {
			return group;
		}
	}

	group = zalloc(1, sizeof(*group));
	if (group == NULL) {
		goto errout;
	}
	safe_strncpy(group->group_name, group_name, DNS_GROUP_NAME_LEN);
	hash_add(dns_group_table.group, &group->node, key);

	return group;
errout:
	if (group) {
		free(group);
	}

	return NULL;
}

int _dns_conf_get_group_set(const char *group_name, struct dns_servers *server)
{
	struct dns_server_groups *group = NULL;
	int i = 0;

	group = _dns_conf_get_group(group_name);
	if (group == NULL) {
		return -1;
	}

	for (i = 0; i < group->server_num; i++) {
		if (group->servers[i] == server) {
			/* already in group */
			return 0;
		}
	}

	if (group->server_num >= DNS_MAX_SERVERS) {
		return -1;
	}

	group->servers[group->server_num] = server;
	group->server_order[group->server_num] = 1000 + (int)(server - dns_conf.servers);
	group->server_num++;

	return 0;
}

int _dns_conf_set_group_order(const char *group_name, struct dns_servers *server, int order)
{
	struct dns_server_groups *group = _dns_conf_get_group(group_name);
	int i = 0;
	if (!group || order < 1 || order > DNS_MAX_SERVERS) {
		return -1;
	}
	for (i = 0; i < group->server_num; i++) {
		if (group->servers[i] == server) {
			group->server_order[i] = order;
			return 0;
		}
	}
	return -1;
}

const char *_dns_conf_get_group_name(const char *group_name)
{
	struct dns_server_groups *group = NULL;

	group = _dns_conf_get_group(group_name);
	if (group == NULL) {
		return NULL;
	}

	return group->group_name;
}

void _config_group_table_init(void)
{
	hash_init(dns_group_table.group);
}

void _config_group_table_destroy(void)
{
	struct dns_server_groups *group = NULL;
	struct hlist_node *tmp = NULL;
	unsigned long i = 0;

	hash_for_each_safe(dns_group_table.group, i, tmp, group, node)
	{
		hlist_del_init(&group->node);
		free(group);
	}
}
