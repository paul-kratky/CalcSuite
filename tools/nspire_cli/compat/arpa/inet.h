/* Windows has no <arpa/inet.h>. libnspire's cx2.cpp only needs htons/ntohs/htonl/ntohl,
   which Winsock provides (link with -lws2_32). Used by tools/build_tools.py. */
#ifndef NSPIRE_CLI_ARPA_INET_H
#define NSPIRE_CLI_ARPA_INET_H
#include <winsock2.h>
#endif
