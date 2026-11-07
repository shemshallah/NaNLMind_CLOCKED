#include "clocked_nan.h"

#include <stdio.h>
#include <string.h>

#if defined(__x86_64__) || defined(_M_X64)
#define CLOCKED_ARCH "x86_64"
#elif defined(__i386__) || defined(_M_IX86)
#define CLOCKED_ARCH "x86"
#elif defined(__aarch64__) || defined(_M_ARM64)
#define CLOCKED_ARCH "aarch64"
#elif defined(__arm__) || defined(_M_ARM)
#define CLOCKED_ARCH "arm"
#elif defined(__riscv)
#define CLOCKED_ARCH "riscv"
#elif defined(__powerpc64__)
#define CLOCKED_ARCH "ppc64"
#elif defined(__wasm__)
#define CLOCKED_ARCH "wasm"
#else
#define CLOCKED_ARCH "generic"
#endif

#if defined(__BYTE_ORDER__) && defined(__ORDER_BIG_ENDIAN__) && \
    __BYTE_ORDER__ == __ORDER_BIG_ENDIAN__
#define CLOCKED_BIG_ENDIAN 1
#else
#define CLOCKED_BIG_ENDIAN 0
#endif

static uint16_t head_for(clocked_nan_type type)
{
    switch (type) {
    case CLOCKED_NAN_SIGNAL_POSITIVE: return 0x7FF1u;
    case CLOCKED_NAN_SIGNAL_NEGATIVE: return 0xFFF1u;
    case CLOCKED_NAN_QUIET_POSITIVE:  return 0x7FF8u;
    case CLOCKED_NAN_QUIET_NEGATIVE:  return 0xFFF8u;
    default: return 0u;
    }
}

static uint8_t class_for(uint16_t head)
{
    switch (head) {
    case 0x7FF1u: return 0u;
    case 0xFFF1u: return 1u;
    case 0x7FF8u: return 2u;
    case 0xFFF8u: return 3u;
    default: return 0xFFu;
    }
}

const char *clocked_arch_name(void) { return CLOCKED_ARCH; }

const char *clocked_arch_endianness(void)
{
    return CLOCKED_BIG_ENDIAN ? "big" : "little";
}

int clocked_arch_is_little_endian(void) { return CLOCKED_BIG_ENDIAN ? 0 : 1; }

clocked_nan16 clocked_nan16_make(clocked_nan_type far_type,
                                clocked_nan_type near_type,
                                uint32_t payload)
{
    const uint16_t f = head_for(far_type);
    const uint16_t n = head_for(near_type);
    clocked_nan16 out;
    out.raw = ((uint64_t)((f >> 8) & 0xFFu)) |
              ((uint64_t)(f & 0xFFu) << 8) |
              ((uint64_t)payload << 16) |
              ((uint64_t)(n & 0xFFu) << 48) |
              ((uint64_t)((n >> 8) & 0xFFu) << 56);
    return out;
}

uint16_t clocked_nan16_far_head(clocked_nan16 word)
{
    return (uint16_t)(((word.raw & 0xFFu) << 8) |
                      ((word.raw >> 8) & 0xFFu));
}

uint16_t clocked_nan16_near_head(clocked_nan16 word)
{
    return (uint16_t)((word.raw >> 48) & 0xFFFFu);
}

uint8_t clocked_nan16_opcode(clocked_nan16 word)
{
    const uint8_t far = class_for(clocked_nan16_far_head(word));
    const uint8_t near = class_for(clocked_nan16_near_head(word));
    if (far == 0xFFu || near == 0xFFu) return 0xFFu;
    return (uint8_t)((near << 2) | far);
}

uint32_t clocked_nan16_payload(clocked_nan16 word)
{
    return (uint32_t)((word.raw >> 16) & 0xFFFFFFFFu);
}

int clocked_nan16_valid(clocked_nan16 word)
{
    return class_for(clocked_nan16_far_head(word)) != 0xFFu &&
           class_for(clocked_nan16_near_head(word)) != 0xFFu;
}

int clocked_nan16_to_bytes(clocked_nan16 word, uint8_t out[8])
{
    const uint16_t far = clocked_nan16_far_head(word);
    const uint16_t near = clocked_nan16_near_head(word);
    const uint32_t payload = clocked_nan16_payload(word);
    if (!out) return 0;
    out[0] = (uint8_t)(far >> 8);
    out[1] = (uint8_t)(far & 0xFFu);
    out[2] = (uint8_t)(payload & 0xFFu);
    out[3] = (uint8_t)((payload >> 8) & 0xFFu);
    out[4] = (uint8_t)((payload >> 16) & 0xFFu);
    out[5] = (uint8_t)((payload >> 24) & 0xFFu);
    out[6] = (uint8_t)(near & 0xFFu);
    out[7] = (uint8_t)(near >> 8);
    return 1;
}

int clocked_nan16_from_bytes(const uint8_t in[8], clocked_nan16 *out)
{
    if (!in || !out) return 0;
    out->raw = (uint64_t)in[0] | ((uint64_t)in[1] << 8);
    out->raw |= ((uint64_t)in[2] |
                 ((uint64_t)in[3] << 8) |
                 ((uint64_t)in[4] << 16) |
                 ((uint64_t)in[5] << 24)) << 16;
    out->raw |= (uint64_t)in[6] << 48;
    out->raw |= (uint64_t)in[7] << 56;
    return clocked_nan16_valid(*out);
}

int clocked_nan16_route_bytes(uint8_t hw_slot, uint8_t out[6])
{
    if (!out || hw_slot == 0u) return 0;
    out[0] = hw_slot;
    out[1] = 0u; /* BS0 */
    out[2] = 0u; /* MC0 */
    out[3] = 0u; /* SC0 */
    out[4] = 0u; /* GM0 */
    out[5] = 0xFFu;
    return 1;
}

int clocked_nan16_route_text(uint8_t hw_slot, char *out, size_t capacity)
{
    int written;
    if (!out || hw_slot == 0u) return 0;
    written = snprintf(out, capacity, "nan://HW%u:BS0:MC0:SC0:GM0",
                       (unsigned)hw_slot);
    return written > 0 && (size_t)written < capacity;
}

static int json_escape(const char *text, char *out, size_t capacity)
{
    size_t used = 0;
    const unsigned char *p = (const unsigned char *)text;
    if (!text || !out || capacity < 3) return 0;
    out[used++] = '"';
    while (*p) {
        unsigned char c = *p++;
        const char *escape = NULL;
        char unicode[7];
        if (c == '"' || c == '\\') {
            if (used + 2 >= capacity) return 0;
            out[used++] = '\\';
            out[used++] = (char)c;
            continue;
        }
        if (c < 0x20u) {
            snprintf(unicode, sizeof(unicode), "\\u%04x", (unsigned)c);
            escape = unicode;
        }
        if (escape) {
            size_t length = strlen(escape);
            if (used + length + 1 >= capacity) return 0;
            memcpy(out + used, escape, length);
            used += length;
        } else {
            if (used + 1 >= capacity) return 0;
            out[used++] = (char)c;
        }
    }
    if (used + 2 > capacity) return 0;
    out[used++] = '"';
    out[used] = '\0';
    return 1;
}

int clocked_nannet_login_body(const char *id_token, uint8_t slot,
                              char *out, size_t capacity)
{
    char escaped[4097];
    int written;
    if (!id_token || slot > 5u || !out || capacity < 32) return 0;
    if (!json_escape(id_token, escaped, sizeof(escaped))) return 0;
    written = snprintf(out, capacity,
                       "{\"id_token\":%s,\"slot\":%u}", escaped,
                       (unsigned)slot);
    return written > 0 && (size_t)written < capacity;
}

int clocked_nannet_auth_header(const char *bearer_token,
                               char *out, size_t capacity)
{
    int written;
    if (!bearer_token || !out || capacity < 16) return 0;
    written = snprintf(out, capacity, "Authorization: Bearer %s", bearer_token);
    return written > 0 && (size_t)written < capacity;
}

int clocked_nannet_login(const char *portal_url, const char *id_token,
                         uint8_t slot, clocked_http_post_fn post,
                         char *response, size_t response_capacity,
                         void *user_data)
{
    char body[8192];
    char url[2048];
    int written;
    if (!portal_url || !portal_url[0] || !post || !response ||
        response_capacity < 2) return 0;
    written = snprintf(url, sizeof(url), "%s%s/v1/bootstrap/oidc",
                       portal_url,
                       portal_url[strlen(portal_url) - 1] == '/' ? "" : "/");
    if (written <= 0 || (size_t)written >= sizeof(url)) return 0;
    if (!clocked_nannet_login_body(id_token, slot, body, sizeof(body))) return 0;
    return post(url, body, strlen(body), response, response_capacity, user_data);
}

uint32_t clocked_nan16_eval_bool(uint8_t opcode, uint32_t a, uint32_t b)
{
    uint32_t result = 0;
    unsigned lane;
    for (lane = 0; lane < 32u; ++lane) {
        const uint32_t index = 2u * ((a >> lane) & 1u) + ((b >> lane) & 1u);
        if ((opcode >> index) & 1u) result |= (uint32_t)1u << lane;
    }
    return result;
}
