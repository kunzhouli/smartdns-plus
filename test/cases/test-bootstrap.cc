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
#include <atomic>

class BootStrap : public ::testing::Test
{
  protected:
	virtual void SetUp() {}
	virtual void TearDown() {}
};

TEST_F(BootStrap, bootstrap)
{
	smartdns::MockServer server_upstream;
	smartdns::MockServer server_upstream2;
	smartdns::Server server;

	server_upstream.Start("udp://0.0.0.0:61053", [](struct smartdns::ServerRequestContext *request) {
		if (request->qtype != DNS_T_A) {
			return smartdns::SERVER_REQUEST_SOA;
		}

		smartdns::MockServer::AddIP(request, request->domain.c_str(), "1.2.3.4", 611);
		return smartdns::SERVER_REQUEST_OK;
	});

	server_upstream2.Start("udp://0.0.0.0:62053", [](struct smartdns::ServerRequestContext *request) {
		if (request->qtype != DNS_T_A) {
			return smartdns::SERVER_REQUEST_SOA;
		}

		smartdns::MockServer::AddIP(request, request->domain.c_str(), "127.0.0.1", 611);
		return smartdns::SERVER_REQUEST_OK;
	});

	server.Start(R"""(bind [::]:60053
server udp://127.0.0.1:62053 -bootstrap-dns
server udp://example.com:61053 -group test
)""");
	smartdns::Client client;
	usleep(2500000);
	ASSERT_TRUE(client.Query("a.com", 60053));
	std::cout << client.GetResult() << std::endl;
	ASSERT_EQ(client.GetAnswerNum(), 1);
	EXPECT_EQ(client.GetStatus(), "NOERROR");
	EXPECT_EQ(client.GetAnswer()[0].GetName(), "a.com");
	EXPECT_EQ(client.GetAnswer()[0].GetData(), "1.2.3.4");
}

TEST_F(BootStrap, group_bootstrap)
{
	std::atomic<int> bootstrap_a_queries{0};
	std::atomic<int> bootstrap_b_queries{0};
	std::atomic<int> wrong_bootstrap_queries{0};
	smartdns::MockServer upstream_a;
	smartdns::MockServer upstream_b;
	smartdns::MockServer bootstrap_a;
	smartdns::MockServer bootstrap_b;
	smartdns::Server server;

	upstream_a.Start("udp://0.0.0.0:63153", [](struct smartdns::ServerRequestContext *request) {
		if (request->qtype != DNS_T_A) {
			return smartdns::SERVER_REQUEST_SOA;
		}
		smartdns::MockServer::AddIP(request, request->domain.c_str(), "1.2.3.4", 611);
		return smartdns::SERVER_REQUEST_OK;
	});
	upstream_b.Start("udp://0.0.0.0:63154", [](struct smartdns::ServerRequestContext *request) {
		if (request->qtype != DNS_T_A) {
			return smartdns::SERVER_REQUEST_SOA;
		}
		smartdns::MockServer::AddIP(request, request->domain.c_str(), "5.6.7.8", 611);
		return smartdns::SERVER_REQUEST_OK;
	});
	bootstrap_a.Start("udp://0.0.0.0:63253", [&](struct smartdns::ServerRequestContext *request) {
		if (request->domain == "dns-a.test") {
			bootstrap_a_queries++;
		} else {
			wrong_bootstrap_queries++;
		}
		if (request->qtype != DNS_T_A) {
			return smartdns::SERVER_REQUEST_SOA;
		}
		smartdns::MockServer::AddIP(request, request->domain.c_str(), "127.0.0.1", 611);
		return smartdns::SERVER_REQUEST_OK;
	});
	bootstrap_b.Start("udp://0.0.0.0:63254", [&](struct smartdns::ServerRequestContext *request) {
		if (request->domain == "dns-b.test") {
			bootstrap_b_queries++;
		} else {
			wrong_bootstrap_queries++;
		}
		if (request->qtype != DNS_T_A) {
			return smartdns::SERVER_REQUEST_SOA;
		}
		smartdns::MockServer::AddIP(request, request->domain.c_str(), "127.0.0.1", 611);
		return smartdns::SERVER_REQUEST_OK;
	});

	server.Start(R"""(bind [::]:63053
server udp://127.0.0.1:63253 -group bootstrap-a -exclude-default-group
server udp://127.0.0.1:63254 -group bootstrap-b -exclude-default-group
server udp://dns-a.test:63153 -group a
server udp://dns-b.test:63154 -group b
priority-nameserver /-.dns-a.test/ bootstrap-a
priority-nameserver /-.dns-b.test/ bootstrap-b
nameserver /a.com/a
nameserver /b.com/b
)""");
	smartdns::Client client;
	usleep(2500000);
	ASSERT_TRUE(client.Query("a.com", 63053));
	ASSERT_EQ(client.GetStatus(), "NOERROR");
	ASSERT_EQ(client.GetAnswerNum(), 1);
	EXPECT_EQ(client.GetAnswer()[0].GetData(), "1.2.3.4");
	ASSERT_TRUE(client.Query("b.com", 63053));
	ASSERT_EQ(client.GetStatus(), "NOERROR");
	ASSERT_EQ(client.GetAnswerNum(), 1);
	EXPECT_EQ(client.GetAnswer()[0].GetData(), "5.6.7.8");
	EXPECT_GT(bootstrap_a_queries, 0);
	EXPECT_GT(bootstrap_b_queries, 0);
	EXPECT_EQ(wrong_bootstrap_queries, 0);
}
