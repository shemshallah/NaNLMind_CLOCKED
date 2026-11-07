#include "clocked_nan.h"

#include <stdio.h>
#include <string.h>

static int failures = 0;
#define CHECK(condition) do { if (!(condition)) { \
    fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #condition); ++failures; } } while (0)

int main(void)
{
    clocked_nan16 word = clocked_nan16_make(
        CLOCKED_NAN_SIGNAL_POSITIVE, CLOCKED_NAN_QUIET_NEGATIVE, 0x12345678u);
    uint8_t bytes[8];
    clocked_nan16 roundtrip;
    char route[64];
    char body[256];
    char auth[128];
    uint8_t raw[6];

    printf("arch=%s endian=%s\n", clocked_arch_name(), clocked_arch_endianness());
    CHECK(clocked_arch_is_little_endian() == 0 || clocked_arch_is_little_endian() == 1);
    CHECK(clocked_nan16_valid(word));
    CHECK(clocked_nan16_far_head(word) == 0x7FF1u);
    CHECK(clocked_nan16_near_head(word) == 0xFFF8u);
    CHECK(clocked_nan16_opcode(word) == 12u);
    CHECK(clocked_nan16_payload(word) == 0x12345678u);
    CHECK(clocked_nan16_to_bytes(word, bytes));
    CHECK(bytes[0] == 0x7Fu && bytes[1] == 0xF1u);
    CHECK(bytes[2] == 0x78u && bytes[5] == 0x12u);
    CHECK(bytes[6] == 0xF8u && bytes[7] == 0xFFu);
    CHECK(clocked_nan16_from_bytes(bytes, &roundtrip));
    CHECK(roundtrip.raw == word.raw);
    CHECK(clocked_nan16_route_bytes(2, raw));
    CHECK(raw[0] == 2u && raw[1] == 0u && raw[5] == 0xFFu);
    CHECK(clocked_nan16_route_text(2, route, sizeof(route)));
    CHECK(strcmp(route, "nan://HW2:BS0:MC0:SC0:GM0") == 0);
    CHECK(clocked_nannet_login_body("header.payload.sig", 4, body, sizeof(body)));
    CHECK(strstr(body, "\"slot\":4") != NULL);
    CHECK(clocked_nannet_auth_header("clu_test", auth, sizeof(auth)));
    CHECK(strcmp(auth, "Authorization: Bearer clu_test") == 0);
    CHECK(clocked_nan16_eval_bool(6u, 0xAAAAAAAAu, 0x55555555u) == 0xFFFFFFFFu);
    CHECK(clocked_nan16_eval_bool(0u, 1u, 1u) == 0u);
    if (failures) return 1;
    puts("clocked_nan: PASS");
    return 0;
}
