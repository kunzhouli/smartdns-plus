#ifndef _DNS_CONF_GEOSITE_H_
#define _DNS_CONF_GEOSITE_H_

#include "set_file.h"

int _config_set_rule_each_from_geosite(const char *file, const char *site, set_rule_add_func callback, void *priv);
int geosite_check_file(const char *file);
int geosite_check_site(const char *file, const char *site);

#endif
