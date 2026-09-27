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

#include "client.h"
#include "smartdns/dns.h"
#include "include/utils.h"
#include "server.h"
#include "gtest/gtest.h"
#include "dns_conf/nameserver.h"
#include "dns_conf/server_group.h"
#include <atomic>

class NameServer : public ::testing::Test
{
  protected:
	virtual void SetUp() {}
	virtual void TearDown() {}
};

TEST_F(NameServer, priority_pattern_matching)
{
	_config_group_table_init();
	INIT_LIST_HEAD(&dns_conf.priority_nameservers);
	char literal[] = "/example.com/";
	char children[] = "/*.child.example/";
	char exact[] = "/-.only.example/";
	char expression[] = "/regex:^api[0-9]+\\.other\\.com$/";
	char duplicate[] = "/example.com/";
	char group1[] = "first";
	char group2[] = "second";
	char *first[] = {(char *)"priority-nameserver", literal, group1};
	char *second[] = {(char *)"priority-nameserver", children, group2};
	char *third[] = {(char *)"priority-nameserver", exact, group2};
	char *fourth[] = {(char *)"priority-nameserver", expression, group2};
	char *fifth[] = {(char *)"priority-nameserver", duplicate, group2};
	ASSERT_EQ(_config_priority_nameserver(NULL, 3, first), 0);
	ASSERT_EQ(_config_priority_nameserver(NULL, 3, second), 0);
	ASSERT_EQ(_config_priority_nameserver(NULL, 3, third), 0);
	ASSERT_EQ(_config_priority_nameserver(NULL, 3, fourth), 0);
	ASSERT_EQ(_config_priority_nameserver(NULL, 3, fifth), 0);
	const auto *match = _config_priority_nameserver_match("www.example.com");
	ASSERT_NE(match, nullptr);
	EXPECT_STREQ(match->group_name, "first");
	match = _config_priority_nameserver_match("www.child.example");
	ASSERT_NE(match, nullptr);
	EXPECT_STREQ(match->group_name, "second");
	match = _config_priority_nameserver_match("API42.OTHER.COM");
	ASSERT_NE(match, nullptr);
	EXPECT_STREQ(match->group_name, "second");
	EXPECT_EQ(_config_priority_nameserver_match("child.example"), nullptr);
	match = _config_priority_nameserver_match("only.example");
	ASSERT_NE(match, nullptr);
	EXPECT_STREQ(match->group_name, "second");
	EXPECT_EQ(_config_priority_nameserver_match("www.only.example"), nullptr);
	match = _config_priority_nameserver_match("api42.other.com");
	ASSERT_NE(match, nullptr);
	EXPECT_STREQ(match->group_name, "second");
	EXPECT_EQ(_config_priority_nameserver_match("api42Xother.com"), nullptr);
	_config_priority_nameserver_destroy();
	_config_group_table_destroy();
}

TEST_F(NameServer, priority_rules_are_strict_and_support_regex)
{
	std::atomic<int> default_queries{0};
	std::atomic<int> fallback_queries{0};
	smartdns::MockServer default_upstream;
	smartdns::MockServer routed_upstream;
	smartdns::MockServer fallback_upstream;
	ASSERT_TRUE(default_upstream.Start("udp://127.0.0.1:64153", [&default_queries](smartdns::ServerRequestContext *request) {
		default_queries++;
		smartdns::MockServer::AddIP(request, request->domain.c_str(), "1.1.1.1", 60);
		return smartdns::SERVER_REQUEST_OK;
	}));
	ASSERT_TRUE(routed_upstream.Start("udp://127.0.0.1:64253", [](smartdns::ServerRequestContext *request) {
		smartdns::MockServer::AddIP(request, request->domain.c_str(), "2.2.2.2", 60);
		return smartdns::SERVER_REQUEST_OK;
	}));
	ASSERT_TRUE(fallback_upstream.Start("udp://127.0.0.1:64353", [&fallback_queries](smartdns::ServerRequestContext *request) {
		fallback_queries++;
		smartdns::MockServer::AddIP(request, request->domain.c_str(), "3.3.3.3", 60);
		return smartdns::SERVER_REQUEST_OK;
	}));
	smartdns::Server server;
	ASSERT_TRUE(server.Start(R"""(bind [::]:64053
server 127.0.0.1:64153
server 127.0.0.1:64253 -group routed -exclude-default-group
server 127.0.0.1:64353 -group fallback -exclude-default-group
domain-rules /example.com/ -address #
domain-rules /example.com/ -nameserver fallback
priority-nameserver /example.com/ routed
priority-nameserver /regex:^api[0-9]+\\.other\\.com$/ routed
priority-nameserver /missing.example/ absent
)"""));
	smartdns::Client client;
	ASSERT_TRUE(client.Query("www.example.com A", 64053));
	ASSERT_EQ(client.GetAnswerNum(), 1);
	EXPECT_EQ(client.GetAnswer()[0].GetData(), "2.2.2.2");
	ASSERT_TRUE(client.Query("api42.other.com A", 64053));
	ASSERT_EQ(client.GetAnswerNum(), 1);
	EXPECT_EQ(client.GetAnswer()[0].GetData(), "2.2.2.2");
	client.Query("missing.example A", 64053);
	EXPECT_EQ(default_queries.load(), 0);
	EXPECT_EQ(fallback_queries.load(), 0);
	ASSERT_TRUE(client.Query("api42Xother.com A", 64053));
	ASSERT_EQ(client.GetAnswerNum(), 1);
	EXPECT_EQ(client.GetAnswer()[0].GetData(), "1.1.1.1");
}

TEST_F(NameServer, cname)
{
	smartdns::MockServer server_upstream;
	smartdns::MockServer server_upstream1;
	smartdns::MockServer server_upstream2;
	smartdns::Server server;

	server_upstream.Start("udp://0.0.0.0:61053", [](struct smartdns::ServerRequestContext *request) {
		if (request->qtype != DNS_T_A) {
			return smartdns::SERVER_REQUEST_SOA;
		}

		smartdns::MockServer::AddIP(request, request->domain.c_str(), "9.10.11.12", 611);
		return smartdns::SERVER_REQUEST_OK;
	});

	server_upstream1.Start("udp://0.0.0.0:62053", [](struct smartdns::ServerRequestContext *request) {
		if (request->qtype != DNS_T_A) {
			return smartdns::SERVER_REQUEST_SOA;
		}

		smartdns::MockServer::AddIP(request, request->domain.c_str(), "1.2.3.4", 611);
		return smartdns::SERVER_REQUEST_OK;
	});

	server_upstream2.Start("udp://0.0.0.0:63053", [](struct smartdns::ServerRequestContext *request) {
		if (request->qtype != DNS_T_A) {
			return smartdns::SERVER_REQUEST_SOA;
		}

		smartdns::MockServer::AddIP(request, request->domain.c_str(), "5.6.7.8", 611);
		return smartdns::SERVER_REQUEST_OK;
	});

	server.Start(R"""(bind [::]:60053
server 127.0.0.1:61053
server 127.0.0.1:62053 -group g1 -exclude-default-group
server 127.0.0.1:63053 -group g2 -exclude-default-group
nameserver /a.com/g1
nameserver /b.com/g2
)""");
	smartdns::Client client;
	ASSERT_TRUE(client.Query("a.com", 60053));
	std::cout << client.GetResult() << std::endl;
	ASSERT_EQ(client.GetAnswerNum(), 1);
	EXPECT_EQ(client.GetStatus(), "NOERROR");
	EXPECT_EQ(client.GetAnswer()[0].GetName(), "a.com");
	EXPECT_EQ(client.GetAnswer()[0].GetData(), "1.2.3.4");

	ASSERT_TRUE(client.Query("b.com", 60053));
	std::cout << client.GetResult() << std::endl;
	ASSERT_EQ(client.GetAnswerNum(), 1);
	EXPECT_EQ(client.GetStatus(), "NOERROR");
	EXPECT_EQ(client.GetAnswer()[0].GetName(), "b.com");
	EXPECT_EQ(client.GetAnswer()[0].GetData(), "5.6.7.8");

	ASSERT_TRUE(client.Query("c.com", 60053));
	std::cout << client.GetResult() << std::endl;
	ASSERT_EQ(client.GetAnswerNum(), 1);
	EXPECT_EQ(client.GetStatus(), "NOERROR");
	EXPECT_EQ(client.GetAnswer()[0].GetName(), "c.com");
	EXPECT_EQ(client.GetAnswer()[0].GetData(), "9.10.11.12");
}
